import sys
import unittest
from unittest import mock

from emulsa import updates


def release(tag="v9.0.0", **over):
    data = {
        "tag_name": tag, "draft": False, "prerelease": False,
        "html_url": "https://github.com/ajr-alves/emulsa/releases/tag/" + tag,
        "body": "## Download\n\nNew things.",
        "assets": [
            {"name": f"EmulsaSetup-{tag[1:]}.exe", "browser_download_url": f"https://github.com/ajr-alves/emulsa/releases/download/{tag}/EmulsaSetup-{tag[1:]}.exe"},
            {"name": f"Emulsa-{tag[1:]}-macOS-arm64.dmg", "browser_download_url": f"https://github.com/ajr-alves/emulsa/releases/download/{tag}/Emulsa-{tag[1:]}-macOS-arm64.dmg"},
            {"name": f"Emulsa-{tag[1:]}-x86_64.AppImage", "browser_download_url": f"https://github.com/ajr-alves/emulsa/releases/download/{tag}/Emulsa-{tag[1:]}-x86_64.AppImage"},
        ],
    }
    data.update(over)
    return data


class FakeStore:
    def __init__(self, **values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class VersionTests(unittest.TestCase):
    def test_comparison(self):
        self.assertTrue(updates.is_newer("0.10.0", "0.9.9"))
        self.assertTrue(updates.is_newer("v1.0.0", "0.3.0"))
        self.assertFalse(updates.is_newer("0.3.0", "0.3.0"))
        self.assertFalse(updates.is_newer("0.2.9", "0.3.0"))
        self.assertFalse(updates.is_newer("latest", "0.3.0"))
        self.assertFalse(updates.is_newer("1.0.0-beta", "0.3.0"))


class SafetyTests(unittest.TestCase):
    def test_only_this_projects_github_links(self):
        self.assertTrue(updates.safe_url("https://github.com/ajr-alves/emulsa/releases/latest"))
        for bad in ("http://github.com/ajr-alves/emulsa/releases", "https://github.com/someone/else/releases",
                    "https://github.com.evil.example/ajr-alves/emulsa/x", "https://evil.example/ajr-alves/emulsa/",
                    "file:///C:/Windows/system32/calc.exe", "javascript:alert(1)", ""):
            self.assertFalse(updates.safe_url(bad), bad)

    def test_hostile_release_links_fall_back_to_the_release_page(self):
        data = release(html_url="https://evil.example/x",
                       assets=[{"name": "EmulsaSetup-9.0.0.exe", "browser_download_url": "https://evil.example/a.exe"}])
        r = updates.parse_release(data)
        self.assertEqual(r.page_url, updates.RELEASES_URL)
        self.assertEqual(r.download_url, updates.RELEASES_URL)

    def test_drafts_prereleases_and_junk_are_ignored(self):
        self.assertIsNone(updates.parse_release(release(draft=True)))
        self.assertIsNone(updates.parse_release(release(prerelease=True)))
        self.assertIsNone(updates.parse_release(release(tag="nightly")))
        self.assertIsNone(updates.parse_release("not a dict"))


class AssetTests(unittest.TestCase):
    def test_picks_the_installer_for_each_system(self):
        for plat, machine, ending in (("win32", "AMD64", ".exe"), ("darwin", "arm64", "arm64.dmg"),
                                      ("linux", "x86_64", ".AppImage")):
            with mock.patch.object(sys, "platform", plat), mock.patch("platform.machine", return_value=machine):
                r = updates.parse_release(release())
                self.assertTrue(r.download_url.endswith(ending), (plat, r.download_url))

    def test_intel_mac_gets_the_release_page(self):
        with mock.patch.object(sys, "platform", "darwin"), mock.patch("platform.machine", return_value="x86_64"):
            self.assertEqual(updates.parse_release(release()).download_url,
                             "https://github.com/ajr-alves/emulsa/releases/tag/v9.0.0")


class ScheduleTests(unittest.TestCase):
    def test_daily_and_respects_the_switch_and_skips(self):
        self.assertTrue(updates.due(FakeStore(), now=1e9))
        self.assertFalse(updates.due(FakeStore(last_update_check=1e9 - 60), now=1e9))
        self.assertFalse(updates.due(FakeStore(check_updates=False), now=1e9))
        r = updates.parse_release(release())
        self.assertTrue(updates.should_announce(r, FakeStore()))
        self.assertFalse(updates.should_announce(r, FakeStore(skipped_version="9.0.0")))
        self.assertFalse(updates.should_announce(None, FakeStore()))


class FetchTests(unittest.TestCase):
    def test_fetch_uses_github_and_handles_no_releases(self):
        calls = []

        class Resp:
            def __init__(self, code, data=None):
                self.status_code, self._data = code, data

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise RuntimeError(self.status_code)

            def json(self):
                return self._data

        class Client:
            def __init__(self, resp):
                self.resp = resp

            def get(self, url):
                calls.append(url)
                return self.resp

        self.assertEqual(updates.fetch_latest(Client(Resp(200, release()))).version, "9.0.0")
        self.assertIsNone(updates.fetch_latest(Client(Resp(404))))
        self.assertEqual(set(calls), {updates.API_URL})


if __name__ == "__main__":
    unittest.main()
