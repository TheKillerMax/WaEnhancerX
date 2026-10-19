import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "app/src/main/res"
PLACEHOLDER = re.compile(r"%(?:\d+\\?\$)?[a-zA-Z]")


def string_resources(folder: Path, *, exclude_files=()):
    resources = {}
    for source in sorted(folder.glob("*.xml")):
        if source.name in exclude_files:
            continue
        for node in ET.parse(source).getroot().findall("string"):
            resources[node.attrib["name"]] = "".join(node.itertext())
    return resources


class SlovenianLocaleTests(unittest.TestCase):
    def test_locale_is_selectable(self):
        helper = (ROOT / "app/src/main/java/com/waenhancer/utils/LocaleHelper.kt").read_text()
        self.assertIn('LanguageOption("sl", "Slovenian", "Slovenščina")', helper)

    def test_locale_keeps_complete_existing_resource_coverage(self):
        default = string_resources(RES / "values")
        # ui_strings.xml externalizes previously hardcoded English interfaces.
        # Those new translations are supplied by the Spanish PR only; Android
        # deliberately falls back to the English default for other languages.
        # Every pre-existing resource group (and future additions to those groups)
        # still requires Slovenian coverage. No existing translation is exempted.
        required = string_resources(RES / "values", exclude_files={"ui_strings.xml"})
        slovenian = string_resources(RES / "values-sl")
        self.assertFalse(set(required) - set(slovenian),
                         f"Missing Slovenian resources: {sorted(set(required) - set(slovenian))}")
        self.assertFalse(set(slovenian) - set(default),
                         f"Unknown Slovenian resources: {sorted(set(slovenian) - set(default))}")

    def test_format_placeholders_match_default_resources(self):
        default = string_resources(RES / "values")
        slovenian = string_resources(RES / "values-sl")
        for name, target_text in slovenian.items():
            source_text = default[name]
            source_args = sorted(value.replace("\\$", "$") for value in PLACEHOLDER.findall(source_text))
            target_args = sorted(value.replace("\\$", "$") for value in PLACEHOLDER.findall(target_text))
            self.assertEqual(source_args, target_args, name)


if __name__ == "__main__":
    unittest.main()
