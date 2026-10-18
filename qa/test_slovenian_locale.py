import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "app/src/main/res"
PLACEHOLDER = re.compile(r"%(?:\d+\\?\$)?[a-zA-Z]")


def string_resources(folder: Path):
    resources = {}
    for source in sorted(folder.glob("*.xml")):
        for node in ET.parse(source).getroot().findall("string"):
            resources[node.attrib["name"]] = "".join(node.itertext())
    return resources


class SlovenianLocaleTests(unittest.TestCase):
    def test_locale_is_selectable(self):
        helper = (ROOT / "app/src/main/java/com/waenhancer/utils/LocaleHelper.kt").read_text()
        self.assertIn('LanguageOption("sl", "Slovenian", "Slovenščina")', helper)

    def test_locale_covers_every_default_string(self):
        default = string_resources(RES / "values")
        slovenian = string_resources(RES / "values-sl")
        self.assertEqual(set(default), set(slovenian))

    def test_format_placeholders_match_default_resources(self):
        default = string_resources(RES / "values")
        slovenian = string_resources(RES / "values-sl")
        for name, source_text in default.items():
            source_args = sorted(value.replace("\\$", "$") for value in PLACEHOLDER.findall(source_text))
            target_args = sorted(value.replace("\\$", "$") for value in PLACEHOLDER.findall(slovenian[name]))
            self.assertEqual(source_args, target_args, name)


if __name__ == "__main__":
    unittest.main()
