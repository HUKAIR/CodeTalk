"""i18n 守护:每个模板里用到的 i18n key(data-i18n* 属性 + t("字面量"))都必须同时
定义在 zh 与 en 字典——否则 t() 静默回落中文,英文用户看到半汉化 UI 且无报错。
本测试就是那道守护(审查发现:无此测试,加 key 漏译不会被发现)。"""
import re
import unittest
from pathlib import Path

PKG = Path(__file__).resolve().parent.parent / "codetalk"
TEMPLATES = ["web_chat", "console", "tunnel", "course", "graph", "trust_ab"]


def _i18n_halves(html):
    """把 var I18N = { zh:{...}, en:{...} } 粗切成 zh / en 两段文本(在 en 字典键处断开)。"""
    m = re.search(r"var I18N\s*=\s*\{", html)
    if not m:
        return None, None
    parts = re.split(r"\ben\s*:\s*\{", html[m.end():], maxsplit=1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]           # zh 段(含 zh:{...}), en 段


def _used_keys(html):
    """静态用到的 i18n key:data-i18n*="k" 属性 + t("k")/t('k') 字面量调用。
    动态拼接的 t("view_"+id) 不在此列(字符串后紧跟 ) 才算),避免误判。"""
    keys = set(re.findall(r'data-i18n(?:-[a-z]+)?="([^"]+)"', html))
    keys |= set(re.findall(r"""\bt\(\s*["']([A-Za-z0-9_]+)["']\s*\)""", html))
    return keys


class TestI18nCoverage(unittest.TestCase):
    def test_every_used_key_defined_in_both_langs(self):
        checked = 0
        for name in TEMPLATES:
            html = (PKG / f"{name}.html").read_text(encoding="utf-8")
            if "var I18N" not in html:
                continue
            zh, en = _i18n_halves(html)
            self.assertIsNotNone(zh, f"{name}: 无法解析 I18N 结构")
            for k in _used_keys(html):
                self.assertRegex(zh, r"\b" + re.escape(k) + r"\s*:",
                                 f"{name}.html: i18n key '{k}' 缺失于 zh 字典")
                self.assertRegex(en, r"\b" + re.escape(k) + r"\s*:",
                                 f"{name}.html: i18n key '{k}' 缺失于 en 字典(会静默回落中文)")
                checked += 1
        self.assertGreater(checked, 30, "应检查到可观数量的 i18n key")


class TestCapsuleOutcomeCanonical(unittest.TestCase):
    """胶囊回写:前端 data-out 必须是后端白名单里的规范中文值,而非翻译后的显示标签。
    (审查发现的 HIGH:tunnel 英文模式 data-out 传 'Overthought it' → 后端 400 → 回写静默失败。)"""

    def test_frontend_posts_only_whitelisted_outcomes(self):
        from codetalk.report import _OUTCOMES
        for name in ["tunnel", "console"]:
            html = (PKG / f"{name}.html").read_text(encoding="utf-8")
            m = re.search(r"var OUTCOMES\s*=\s*(\[\[.*?\]\])", html)
            self.assertIsNotNone(m, f"{name}: 未找到 OUTCOMES 列表")
            canon = re.findall(r'\[\s*"[^"]+"\s*,\s*"([^"]+)"\s*\]', m.group(1))
            self.assertTrue(canon, f"{name}: 未解析出 canonical outcome")
            for c in canon:
                self.assertIn(c, _OUTCOMES,
                              f"{name}.html: 前端 data-out '{c}' 不在后端 _OUTCOMES 白名单"
                              "(英文模式回写会 400)")


if __name__ == "__main__":
    unittest.main()
