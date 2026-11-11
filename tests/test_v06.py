"""v0.6.0: similar photos (dHash over Windows shell thumbnails)."""

import math
import os
import random
import unittest

from spacesweep import imaging, photos, winapi
from spacesweep.jobs import Job

from .test_core import TempCase, write


def picture(w, h, fn):
    px = bytearray()
    for y in range(h):
        for x in range(w):
            r, g, b = fn(x / w, y / h)
            px += bytes((max(0, min(255, int(r))), max(0, min(255, int(g))), max(0, min(255, int(b))), 255))
    return imaging.png(w, h, bytes(px))


def scene(x, y):
    return (255 * x, 128 + 100 * math.sin(6 * y), 255 * (1 - x) * y)


class HashTests(unittest.TestCase):
    def test_dhash_similar_and_different(self):
        def bgra(fn, w=64, h=48, noise=0):
            rnd = random.Random(1)
            out = bytearray()
            for y in range(h):
                for x in range(w):
                    r, g, b = fn(x / w, y / h)
                    n = rnd.randint(-noise, noise)
                    out += bytes((max(0, min(255, int(b + n))), max(0, min(255, int(g + n))), max(0, min(255, int(r + n))), 255))
            return w, h, bytes(out)

        base = photos.dhash(*bgra(scene))
        noisy = photos.dhash(*bgra(scene, noise=6))
        resized = photos.dhash(*bgra(scene, w=100, h=75))
        other = photos.dhash(*bgra(lambda x, y: (255 * y, 255 * (1 - y), 128 + 120 * math.cos(9 * x))))
        dist = lambda a, b: bin(a ^ b).count("1")
        self.assertLessEqual(dist(base, noisy), 6)
        self.assertLessEqual(dist(base, resized), 6)
        self.assertGreater(dist(base, other), 16)

    def test_grouping_with_bands(self):
        items = [("a", 0b1011 << 40), ("b", (0b1011 << 40) ^ 0b111), ("c", ~(0b1011 << 40) & (2 ** 64 - 1)), ("d", (0b1011 << 40) ^ (1 << 63))]
        groups = sorted(sorted(g) for g in photos.group_hashes(items, 4))
        self.assertEqual(groups, [["a", "b", "d"]])


@unittest.skipUnless(winapi.IS_WINDOWS and not os.environ.get("GITHUB_ACTIONS"),
                     "uses the Windows shell thumbnail API (not available in CI's non-interactive session)")
class ShellThumbnailTests(TempCase):
    def test_find_similar_on_real_files(self):
        folder = self.p("Pictures")
        write(os.path.join(folder, "beach.png"), picture(320, 240, scene))
        write(os.path.join(folder, "beach-edited.png"), picture(320, 240, lambda x, y: tuple(c * 0.92 + 8 for c in scene(x, y))))
        write(os.path.join(folder, "beach-small.png"), picture(160, 120, scene))
        write(os.path.join(folder, "forest.png"), picture(320, 240, lambda x, y: (255 * y, 255 * (1 - y), 128 + 120 * math.cos(9 * x))))
        res = photos.find_similar(Job("t"), [folder], threshold=8, min_size=0)
        self.assertEqual(res["hashed"], 4)
        self.assertEqual(res["total_groups"], 1)
        names = sorted(os.path.basename(f["path"]) for f in res["groups"][0]["files"])
        self.assertEqual(names, ["beach-edited.png", "beach-small.png", "beach.png"])
        uri = photos.thumb_data_uri(os.path.join(folder, "forest.png"), 80)
        self.assertTrue(uri.startswith("data:image/png;base64,"))


if __name__ == "__main__":
    unittest.main()
