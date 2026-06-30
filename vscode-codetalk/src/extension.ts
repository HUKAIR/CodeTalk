import * as vscode from 'vscode';
import { execFile } from 'child_process';
import { promisify } from 'util';

const exec = promisify(execFile);

interface TestRef { path: string; names: string[]; }
interface PrRef { number: number; title: string; snippet: string; }

interface BlameSegment {
  sha: string;
  date: string;
  subject: string;
  why: string;
  decisions: string[];
  risks: string[];
  rejected: string[];
  evidence: unknown[];
  test_refs: TestRef[];
  pr_refs: PrRef[];
}

interface FileBlameData {
  segments: BlameSegment[];
  lineMap: Map<number, string>;
}

const blameCache = new Map<string, FileBlameData>();
const expandedState = new Map<string, Set<string>>();

function segmentHasWhy(seg: BlameSegment): boolean {
  return !!(
    seg.why?.trim() ||
    seg.decisions?.length ||
    seg.rejected?.length ||
    seg.evidence?.length
  );
}

async function fetchBlameData(
  filePath: string,
  workspaceRoot: string
): Promise<FileBlameData | null> {
  const config = vscode.workspace.getConfiguration('codetalk');
  const pythonPath = config.get<string>('pythonPath', 'python3');

  let segments: BlameSegment[];
  try {
    const { stdout } = await exec(
      pythonPath,
      ['-m', 'codetalk', 'blame', filePath, '--json', '--project', workspaceRoot],
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
  md.isTrusted = { enabledCommands: ['workbench.action.terminal.sendSequence'] };
  const sha7 = seg.sha.slice(0, 7);
  const date = escapeMarkdown((seg.date || '').slice(0, 10));

  md.appendMarkdown(`**[${sha7}]** ${date} · ${escapeMarkdown(seg.subject)}\n\n`);
  if (seg.why) md.appendMarkdown(`**Why:** ${escapeMarkdown(seg.why)}\n\n`);
  if (seg.decisions?.length) {
    md.appendMarkdown('**Decisions:**\n');
    for (const d of seg.decisions) md.appendMarkdown(`- ${escapeMarkdown(d)}\n`);
    md.appendMarkdown('\n');
  }
  if (seg.rejected?.length) {
    md.appendMarkdown('**Rejected:**\n');
    for (const r of seg.rejected) md.appendMarkdown(`- ${escapeMarkdown(r)}\n`);
    md.appendMarkdown('\n');
  }
  if (seg.risks?.length) {
    md.appendMarkdown('**Risks:**\n');
    for (const r of seg.risks) md.appendMarkdown(`- ${escapeMarkdown(r)}\n`);
    md.appendMarkdown('\n');
  }
  if (seg.test_refs?.length) {
    md.appendMarkdown('**Tests:**\n');
    for (const t of seg.test_refs) {
      const names = t.names?.join(', ') || '(no explicit tests)';
      md.appendMarkdown(`- ${escapeMarkdown(t.path)} — ${escapeMarkdown(names)}\n`);
    }
    md.appendMarkdown('\n');
  }
  if (seg.pr_refs?.length) {
    md.appendMarkdown('**PR context:**\n');
    for (const p of seg.pr_refs)
      md.appendMarkdown(
        `- #${p.number} ${escapeMarkdown(p.title)} — ${escapeMarkdown(p.snippet)}\n`
      );
    md.appendMarkdown('\n');
  }
  md.appendMarkdown('---\n\n');
  const termArgs = encodeURIComponent(JSON.stringify({ text: `git show ${sha7}\n` }));
  md.appendMarkdown(
    `[\`git show ${sha7}\`](command:workbench.action.terminal.sendSequence?${termArgs})` +
      ' · codetalk blame'
  );
  return md;
}

function escapeMarkdown(s: string | undefined): string {
  return (s ?? '').replace(/([\\`*_{}\[\]()#+\-.!|>])/g, '\\$1');
}

function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max - 3) + '...' : s;
}

class CodetalkCodeLensProvider implements vscode.CodeLensProvider {
  private _onDidChange = new vscode.EventEmitter<void>();
  readonly onDidChangeCodeLenses = this._onDidChange.event;

  refresh(): void { this._onDidChange.fire(); }

  provideCodeLenses(document: vscode.TextDocument): vscode.CodeLens[] {
    const config = vscode.workspace.getConfiguration('codetalk');
    if (!config.get<boolean>('enabled', true)) return [];

    const data = blameCache.get(document.uri.fsPath);
    if (!data) return [];

    const expanded = expandedState.get(document.uri.fsPath) ?? new Set();
    const segBySha = new Map<string, BlameSegment>();
    for (const seg of data.segments) segBySha.set(seg.sha, seg);

    const lenses: vscode.CodeLens[] = [];
    const rendered = new Set<string>();
    const lines = [...data.lineMap.entries()].sort((a, b) => a[0] - b[0]);

    for (const [line, sha] of lines) {
      // one card per commit file-wide: a commit touching interleaved regions
      // would otherwise repeat its full expanded decision tree at every region
      if (rendered.has(sha)) continue;

      const seg = segBySha.get(sha);
      if (!seg || !segmentHasWhy(seg)) continue;
      rendered.add(sha);

      const sha7 = sha.slice(0, 7);
      const range = new vscode.Range(line, 0, line, 0);
      const toggleArgs = [document.uri.fsPath, sha];

      if (expanded.has(sha)) {
        const date = (seg.date || '').slice(0, 10);
        lenses.push(new vscode.CodeLens(range, {
          title: `▾ ${sha7} · ${date} · ${truncate(seg.subject, 60)}`,
          command: 'codetalk.toggleBlame',
          arguments: toggleArgs,
        }));
        if (seg.why) {
          lenses.push(new vscode.CodeLens(range, {
            title: `    Why: ${truncate(seg.why, 80)}`,
            command: 'codetalk.toggleBlame',
            arguments: toggleArgs,
          }));
        }
        for (const d of seg.decisions ?? []) {
          lenses.push(new vscode.CodeLens(range, {
            title: `    决策: ${truncate(d, 70)}`,
            command: 'codetalk.toggleBlame',
            arguments: toggleArgs,
          }));
        }
        for (const r of seg.rejected ?? []) {
          lenses.push(new vscode.CodeLens(range, {
            title: `    否决: ${truncate(r, 70)}`,
            command: 'codetalk.toggleBlame',
            arguments: toggleArgs,
          }));
        }
        for (const r of seg.risks ?? []) {
          lenses.push(new vscode.CodeLens(range, {
            title: `    风险: ${truncate(r, 70)}`,
            command: 'codetalk.toggleBlame',
            arguments: toggleArgs,
          }));
        }
      } else {
        const counts: string[] = [];
        if (seg.decisions?.length) counts.push(`决策(${seg.decisions.length})`);
        if (seg.rejected?.length) counts.push(`否决(${seg.rejected.length})`);
        if (seg.risks?.length) counts.push(`风险(${seg.risks.length})`);
        const summary = counts.join(' ') || 'why';
        lenses.push(new vscode.CodeLens(range, {
          title: `▸ ${sha7} · ${summary}`,
          command: 'codetalk.toggleBlame',
          arguments: toggleArgs,
        }));
      }
    }
    return lenses;
  }
}

export function activate(context: vscode.ExtensionContext): void {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return;

  execFile('git', ['rev-parse', '--git-dir'], { cwd: ws.uri.fsPath }, (err: Error | null) => {
    if (err) return;

    const codeLensProvider = new CodetalkCodeLensProvider();

    context.subscriptions.push(
      vscode.commands.registerCommand(
        'codetalk.toggleBlame',
        (filePath: string, sha: string) => {
          let set = expandedState.get(filePath);
          if (!set) { set = new Set(); expandedState.set(filePath, set); }
          if (set.has(sha)) set.delete(sha);
          else set.add(sha);
          codeLensProvider.refresh();
        }
      ),
      vscode.commands.registerCommand('codetalk.expandAll', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;
        const data = blameCache.get(editor.document.uri.fsPath);
        if (!data) return;
        const set = new Set(data.segments.filter(segmentHasWhy).map(s => s.sha));
        expandedState.set(editor.document.uri.fsPath, set);
        codeLensProvider.refresh();
      }),
      vscode.commands.registerCommand('codetalk.collapseAll', () => {
        const editor = vscode.window.activeTextEditor;
        if (!editor) return;
        expandedState.delete(editor.document.uri.fsPath);
        codeLensProvider.refresh();
      })
    );

    context.subscriptions.push(
      vscode.languages.registerCodeLensProvider('*', codeLensProvider)
    );

    context.subscriptions.push(
      vscode.languages.registerHoverProvider('*', {
        provideHover(document, position) {
          const data = blameCache.get(document.uri.fsPath);
          if (!data) return null;
          const sha = data.lineMap.get(position.line);
          if (!sha) return null;
          const seg = data.segments.find((s) => s.sha === sha);
          if (!seg || !segmentHasWhy(seg)) return null;
          return new vscode.Hover(buildHoverCard(seg));
        },
      })
    );

    async function refresh(editor?: vscode.TextEditor): Promise<void> {
      if (!editor) return;
      const config = vscode.workspace.getConfiguration('codetalk');
      if (!config.get<boolean>('enabled', true)) return;
      const filePath = vscode.workspace.asRelativePath(editor.document.uri);
      const data = await fetchBlameData(filePath, ws!.uri.fsPath);
      if (data) {
        blameCache.set(editor.document.uri.fsPath, data);
        codeLensProvider.refresh();
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
      }),
      vscode.workspace.onDidChangeConfiguration((e) => {
        if (!e.affectsConfiguration('codetalk')) return;
        codeLensProvider.refresh();
      })
    );

    if (vscode.window.activeTextEditor) {
      refresh(vscode.window.activeTextEditor);
    }
  });
}

export function deactivate(): void {
  blameCache.clear();
  expandedState.clear();
}
