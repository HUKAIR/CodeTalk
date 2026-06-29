import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const exec = promisify(execFile);

interface BlameSegment {
  sha: string;
  date: string;
  subject: string;
  why: string;
  decisions: string[];
  risks: string[];
  rejected: string[];
  evidence: unknown[];
}

interface FileBlameData {
  segments: BlameSegment[];
  lineMap: Map<number, string>;
}

const blameCache = new Map<string, FileBlameData>();
let decorationType: vscode.TextEditorDecorationType;

function segmentHasWhy(seg: BlameSegment): boolean {
  return !!(
    seg.why?.trim() ||
    seg.decisions?.length ||
    seg.rejected?.length ||
    (seg.evidence as unknown[])?.length
  );
}

async function fetchBlameData(
  filePath: string,
  workspaceRoot: string
): Promise<FileBlameData | null> {
  const config = vscode.workspace.getConfiguration('vibetrace');
  const pythonPath = config.get<string>('pythonPath', 'python3');

  let segments: BlameSegment[];
  try {
    const { stdout } = await exec(
      pythonPath,
      ['-m', 'vibetrace', 'blame', filePath, '--json', '--project', workspaceRoot],
      { cwd: workspaceRoot, timeout: 10_000 }
    );
    segments = JSON.parse(stdout);
  } catch {
    return null;
  }

  const lineMap = new Map<number, string>();
  try {
    const { stdout } = await exec(
      'git',
      ['blame', '--porcelain', filePath],
      { cwd: workspaceRoot, timeout: 10_000 }
    );
    for (const line of stdout.split('\n')) {
      const m = line.match(/^([0-9a-f]{40}) \d+ (\d+)/);
      if (m) lineMap.set(parseInt(m[2], 10) - 1, m[1]);
    }
  } catch {
    return null;
  }

  return { segments, lineMap };
}

function buildHoverCard(seg: BlameSegment): vscode.MarkdownString {
  const md = new vscode.MarkdownString();
  md.isTrusted = true;
  const sha7 = seg.sha.slice(0, 7);
  const date = (seg.date || '').slice(0, 10);

  md.appendMarkdown(`**[${sha7}]** ${date} · ${seg.subject}\n\n`);
  if (seg.why) {
    md.appendMarkdown(`**Why:** ${seg.why}\n\n`);
  }
  if (seg.decisions?.length) {
    md.appendMarkdown('**Decisions:**\n');
    for (const d of seg.decisions) md.appendMarkdown(`- ${d}\n`);
    md.appendMarkdown('\n');
  }
  if (seg.rejected?.length) {
    md.appendMarkdown('**Rejected:**\n');
    for (const r of seg.rejected) md.appendMarkdown(`- ${r}\n`);
    md.appendMarkdown('\n');
  }
  if (seg.risks?.length) {
    md.appendMarkdown('**Risks:**\n');
    for (const r of seg.risks) md.appendMarkdown(`- ${r}\n`);
    md.appendMarkdown('\n');
  }
  md.appendMarkdown('---\n\n');
  const termArgs = encodeURIComponent(
    JSON.stringify({ text: `git show ${sha7}\n` })
  );
  md.appendMarkdown(
    `[\`git show ${sha7}\`](command:workbench.action.terminal.sendSequence?${termArgs})` +
      ' · vibetrace blame'
  );
  return md;
}

function applyDecorations(
  editor: vscode.TextEditor,
  data: FileBlameData
): void {
  const segBySha = new Map<string, BlameSegment>();
  for (const seg of data.segments) segBySha.set(seg.sha, seg);

  const decorations: vscode.DecorationOptions[] = [];
  let prevSha: string | null = null;

  for (let line = 0; line < editor.document.lineCount; line++) {
    const sha = data.lineMap.get(line);
    if (!sha) {
      prevSha = null;
      continue;
    }
    if (sha === prevSha) continue;
    prevSha = sha;

    const seg = segBySha.get(sha);
    if (!seg || !segmentHasWhy(seg)) continue;

    const sha7 = sha.slice(0, 7);
    const label = seg.decisions?.[0] || seg.why || '';
    let text = ` ${sha7} · ${label}`;
    if (text.length > 80) text = text.slice(0, 77) + '...';

    decorations.push({
      range: new vscode.Range(line, Infinity, line, Infinity),
      renderOptions: {
        after: {
          contentText: text,
          color: new vscode.ThemeColor('editorInlayHint.foreground'),
          fontStyle: 'italic',
        },
      },
    });
  }
  editor.setDecorations(decorationType, decorations);
}

export function activate(context: vscode.ExtensionContext): void {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return;

  execFile(
    'git',
    ['rev-parse', '--git-dir'],
    { cwd: ws.uri.fsPath },
    (err) => {
      if (err) return;

      decorationType = vscode.window.createTextEditorDecorationType({});
      context.subscriptions.push(decorationType);

      const hoverProvider = vscode.languages.registerHoverProvider('*', {
        provideHover(document, position) {
          const data = blameCache.get(document.uri.fsPath);
          if (!data) return null;
          const sha = data.lineMap.get(position.line);
          if (!sha) return null;
          const seg = data.segments.find((s) => s.sha === sha);
          if (!seg || !segmentHasWhy(seg)) return null;
          return new vscode.Hover(buildHoverCard(seg));
        },
      });
      context.subscriptions.push(hoverProvider);

      async function refresh(editor?: vscode.TextEditor): Promise<void> {
        if (!editor) return;
        const config = vscode.workspace.getConfiguration('vibetrace');
        if (!config.get<boolean>('enabled', true)) return;

        const filePath = vscode.workspace.asRelativePath(editor.document.uri);
        const data = await fetchBlameData(filePath, ws!.uri.fsPath);
        if (data) {
          blameCache.set(editor.document.uri.fsPath, data);
          applyDecorations(editor, data);
        }
      }

      context.subscriptions.push(
        vscode.window.onDidChangeActiveTextEditor(refresh),
        vscode.workspace.onDidSaveTextDocument(() => {
          const editor = vscode.window.activeTextEditor;
          if (editor) {
            blameCache.delete(editor.document.uri.fsPath);
            refresh(editor);
          }
        })
      );

      if (vscode.window.activeTextEditor) {
        refresh(vscode.window.activeTextEditor);
      }
    }
  );
}

export function deactivate(): void {
  blameCache.clear();
}
