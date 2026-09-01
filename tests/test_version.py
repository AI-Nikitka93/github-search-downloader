from __future__ import annotations

import unittest
from github_harvester.version import (
    APP_DISPLAY_NAME,
    APP_NAME,
    CURRENT_SEMVER,
    SemVer,
    __version__,
)


class TestSemVer(unittest.TestCase):
    def test_semver_parse_valid(self):
        v = SemVer.parse("1.2.3")
        self.assertEqual(v.major, 1)
        self.assertEqual(v.minor, 2)
        self.assertEqual(v.patch, 3)
        self.assertEqual(v.prerelease, "")
        self.assertEqual(v.build, "")
        self.assertEqual(str(v), "1.2.3")

    def test_semver_parse_with_v_prefix(self):
        v = SemVer.parse("v2.0.4-beta.1+build.123")
        self.assertEqual(v.major, 2)
        self.assertEqual(v.minor, 0)
        self.assertEqual(v.patch, 4)
        self.assertEqual(v.prerelease, "beta.1")
        self.assertEqual(v.build, "build.123")
        self.assertEqual(str(v), "2.0.4-beta.1+build.123")

    def test_semver_parse_invalid(self):
        with self.assertRaises(ValueError):
            SemVer.parse("not-a-version")
        with self.assertRaises(ValueError):
            SemVer.parse("1.2")

    def test_semver_comparisons(self):
        v100 = SemVer.parse("1.0.0")
        v110 = SemVer.parse("1.1.0")
        v111 = SemVer.parse("1.1.1")
        v200 = SemVer.parse("2.0.0")

        self.assertTrue(v100 < v110)
        self.assertTrue(v110 < v111)
        self.assertTrue(v111 < v200)
        self.assertTrue(v200 > v100)
        self.assertEqual(v100, SemVer.parse("1.0.0"))
        self.assertNotEqual(v100, v110)

    def test_semver_prerelease_comparison_numeric_and_lexical(self):
        # 1.0.0-alpha < 1.0.0-alpha.1 < 1.0.0-alpha.beta < 1.0.0-beta < 1.0.0-beta.2 < 1.0.0-beta.11 < 1.0.0-rc.1 < 1.0.0
        v_alpha = SemVer.parse("1.0.0-alpha")
        v_alpha_1 = SemVer.parse("1.0.0-alpha.1")
        v_alpha_2 = SemVer.parse("1.0.0-alpha.2")
        v_alpha_10 = SemVer.parse("1.0.0-alpha.10")
        v_alpha_beta = SemVer.parse("1.0.0-alpha.beta")
        v_beta = SemVer.parse("1.0.0-beta")
        v_beta_2 = SemVer.parse("1.0.0-beta.2")
        v_beta_11 = SemVer.parse("1.0.0-beta.11")
        v_rc_1 = SemVer.parse("1.0.0-rc.1")
        v_release = SemVer.parse("1.0.0")

        self.assertTrue(v_alpha < v_alpha_1)
        self.assertTrue(v_alpha_1 < v_alpha_2)
        self.assertTrue(v_alpha_2 < v_alpha_10)  # Numeric 2 < 10
        self.assertTrue(v_alpha_10 < v_alpha_beta)  # Numeric < Non-numeric
        self.assertTrue(v_alpha_beta < v_beta)
        self.assertTrue(v_beta < v_beta_2)
        self.assertTrue(v_beta_2 < v_beta_11)  # Numeric 2 < 11
        self.assertTrue(v_beta_11 < v_rc_1)
        self.assertTrue(v_rc_1 < v_release)

    def test_to_pe_tuple(self):
        v = SemVer.parse("1.2.3")
        self.assertEqual(v.to_pe_tuple(), (1, 2, 3, 0))

    def test_current_version_constants(self):
        self.assertIsInstance(__version__, str)
        self.assertEqual(str(CURRENT_SEMVER), __version__)
        self.assertTrue(len(APP_NAME) > 0)
        self.assertTrue(len(APP_DISPLAY_NAME) > 0)


if __name__ == "__main__":
    unittest.main()
