"""v0.4.0: inventory (VDF parsing, Steam, families, editor/IDE leftovers, LM Studio runtimes, AI models)."""

import json
import os
import time
import unittest
from unittest import mock

from spacesweep import inventory

from .test_core import TempCase, write


class ParsingTests(unittest.TestCase):
    def test_vdf(self):
        text = '"AppState" { "appid" "570" "name" "Dota 2" "SizeOnDisk" "123" "UserConfig" { "language" "spanish" } ' \
               '"installdir" "dota 2 beta" "path" "D:\\\\SteamLibrary" }'
        d = inventory.parse_vdf(text)["appstate"]
        self.assertEqual((d["appid"], d["sizeondisk"], d["userconfig"]["language"]), ("570", "123", "spanish"))
        self.assertEqual(d["path"], "D:\\SteamLibrary")

    def test_split_command(self):
        self.assertEqual(inventory.split_command('"C:\\Program Files\\App\\unins000.exe" /SILENT'),
                         ("C:\\Program Files\\App\\unins000.exe", "/SILENT"))
        self.assertEqual(inventory.split_command("MsiExec.exe /I{33F6AA45-05AE-4040}"), ("MsiExec.exe", "/X{33F6AA45-05AE-4040}"))
        self.assertEqual(inventory.split_command("C:\\Tools\\un.exe --remove"), ("C:\\Tools\\un.exe", "--remove"))

    def test_family_keys(self):
        fk = inventory.family_key
        self.assertEqual(fk("Microsoft SQL Server Management Studio - 19.1"), fk("SQL Server Management Studio 21"))
        self.assertEqual(fk("Python 3.12.2 (64-bit)"), fk("Python 3.11.9 (64-bit)"))
        self.assertEqual(fk("Visual Studio Build Tools 2019"), fk("Visual Studio Build Tools 2022"))
        self.assertNotEqual(fk("Python 3.12.2 Core Interpreter (64-bit)"), fk("Java 8 Update 401"))


class SteamTests(TempCase):
    def test_games_libraries_and_last_played(self):
        root = self.p("Steam")
        lib2 = self.p("Lib2")
        write(os.path.join(root, "steamapps", "libraryfolders.vdf"),
              f'"libraryfolders" {{ "0" {{ "path" "{root.replace(chr(92), chr(92) * 2)}" }} "1" {{ "path" "{lib2.replace(chr(92), chr(92) * 2)}" }} }}')
        write(os.path.join(root, "steamapps", "appmanifest_10.acf"),
              '"AppState" { "appid" "10" "name" "Old Game" "installdir" "old" "SizeOnDisk" "5000" }')
        write(os.path.join(lib2, "steamapps", "appmanifest_20.acf"),
              '"AppState" { "appid" "20" "name" "New Game" "installdir" "new" "SizeOnDisk" "9000" "LastPlayed" "1700000000" }')
        write(os.path.join(root, "steamapps", "appmanifest_228980.acf"), '"AppState" { "appid" "228980" "name" "Redist" }')
        played = int(time.time()) - 100 * 86400
        write(os.path.join(root, "userdata", "123", "config", "localconfig.vdf"),
              f'"UserLocalConfigStore" {{ "Software" {{ "Valve" {{ "Steam" {{ "apps" {{ "10" {{ "LastPlayed" "{played}" "cloud" {{ "x" "1" }} }} }} }} }} }} }}')
        games = {g["id"]: g for g in inventory.steam_games(root)}
        self.assertEqual(set(games), {"10", "20"})
        self.assertEqual(games["10"]["last_played"], played)
        self.assertEqual(games["20"]["last_played"], 1700000000)
        self.assertEqual(games["20"]["path"], os.path.join(lib2, "steamapps", "common", "new"))
        self.assertEqual(games["10"]["size"], 5000)


class LeftoverTests(TempCase):
    def test_vscode_obsolete_and_old_versions(self):
        ext = self.p("home", ".vscode", "extensions")
        for name in ("ms-python.python-2024.1.0", "ms-python.python-2024.2.0", "foo.bar-1.0.0", "foo.bar-1.1.0", "solo.ext-3.0.0"):
            write(os.path.join(ext, name, "package.json"), b"{}")
        write(os.path.join(ext, ".obsolete"), json.dumps({"foo.bar-1.0.0": True}))
        write(os.path.join(ext, "extensions.json"), json.dumps([
            {"relativeLocation": "ms-python.python-2024.2.0"}, {"relativeLocation": "foo.bar-1.1.0"}, {"relativeLocation": "solo.ext-3.0.0"}]))
        with mock.patch.object(inventory, "HOME", self.p("home")):
            found = {x["name"]: x["reason"] for x in inventory.vscode_leftovers()}
        self.assertEqual(found, {"foo.bar-1.0.0": "obsolete", "ms-python.python-2024.1.0": "old_version"})

    def test_jetbrains_keeps_newest(self):
        roam = self.p("roam", "JetBrains")
        for n in ("PyCharm2023.2", "PyCharm2024.1", "PyCharm2024.3", "IntelliJIdea2024.2", "consentOptions"):
            write(os.path.join(roam, n, "x.txt"))
        with mock.patch.object(inventory, "ROAM", self.p("roam")), mock.patch.object(inventory, "LOCAL", self.p("none")):
            found = sorted(x["name"] for x in inventory.jetbrains_leftovers())
        self.assertEqual(found, ["PyCharm2023.2", "PyCharm2024.1"])

    def test_lmstudio_runtimes_keep_newest_and_selected(self):
        base = self.p("lms")
        b = os.path.join(base, "extensions", "backends")
        for n in ("llama.cpp-win-cuda-1.9.0", "llama.cpp-win-cuda-1.10.0", "llama.cpp-win-cuda-1.2.0", "llama.cpp-win-vulkan-1.0.0", "vendor"):
            write(os.path.join(b, n, "x.dll"), b"d" * 10)
        write(os.path.join(base, ".internal", "backend-preferences-v1.json"), '{"selected": "llama.cpp-win-cuda-1.2.0"}')
        write(os.path.join(base, ".internal", "download-jobs-info.json"), '"llama.cpp-win-cuda-1.9.0"')  # history, ignored
        found = sorted(x["name"] for x in inventory.lmstudio_runtimes(base))
        self.assertEqual(found, ["llama.cpp-win-cuda-1.9.0"])  # 1.10 newest (numeric, not text order), 1.2 selected


class ModelTests(TempCase):
    def test_lmstudio_hf_and_ollama(self):
        home = self.p("home")
        write(os.path.join(home, ".lmstudio", "models", "pub", "Model-GGUF", "m.gguf"), b"g" * 100)
        hub = self.p("hf", "hub")
        write(os.path.join(hub, "models--org--tiny", "blobs", "b1"), b"h" * 50)
        oll = self.p("ollama")
        write(os.path.join(oll, "manifests", "registry.ollama.ai", "library", "llama3", "8b"),
              json.dumps({"layers": [{"size": 4000}, {"size": 96}]}))
        env = {"HF_HUB_CACHE": hub, "OLLAMA_MODELS": oll}
        with mock.patch.object(inventory, "HOME", home), mock.patch.dict(os.environ, env), \
                mock.patch.object(inventory.shutil, "which", lambda name: None):
            res = inventory.ai_models()
        got = {(m["app"], m["name"]): (m["size"], m["delete"]) for m in res["models"]}
        self.assertEqual(got[("LM Studio", "pub/Model-GGUF")], (100, "folder"))
        self.assertEqual(got[("Hugging Face", "org/tiny")], (50, "folder"))
        self.assertEqual(got[("Ollama", "llama3:8b")], (4096, "none"))
        self.assertEqual(res["total"], 4246)


if __name__ == "__main__":
    unittest.main()
