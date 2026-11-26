import unittest

from recursion_storage import BACKING_RESERVE, GROUP_SIZE, LINUX_RESERVE, required_scratch, select


class RecursionStorageTests(unittest.TestCase):
    shards = 40_000
    index = 'ab' * 32
    scratch = required_scratch(shards)

    def test_larger_groups_reduce_the_retained_tree_budget(self):
        self.assertEqual(self.scratch, 1_184_366_592)
        self.assertGreater(required_scratch(self.shards, group_size=32), 3 * self.scratch)
        self.assertEqual(GROUP_SIZE, 128)

    def test_prefers_checkpoint_with_enough_space(self):
        site = select(self.shards, self.index, LINUX_RESERVE + self.scratch, 0, 0)
        self.assertEqual(site['site'], 'checkpoint')
        self.assertEqual(site['group_size'], 128)

    def test_backing_requires_both_host_and_linux_space(self):
        host = BACKING_RESERVE + self.scratch
        linux = LINUX_RESERVE + self.scratch
        site = select(self.shards, self.index, LINUX_RESERVE, linux, host)
        self.assertEqual(site['site'], 'backing')
        for linux_free, host_free in ((linux - 1, host), (linux, host - 1), (linux, 0)):
            with self.assertRaisesRegex(ValueError, 'neither recursion workspace'):
                select(self.shards, self.index, LINUX_RESERVE, linux_free, host_free)

    def test_resume_pins_the_location_and_archive(self):
        prior = select(self.shards, self.index, LINUX_RESERVE, LINUX_RESERVE + self.scratch,
                       BACKING_RESERVE + self.scratch)
        self.assertEqual(select(self.shards, self.index, 100 * LINUX_RESERVE, LINUX_RESERVE,
                                BACKING_RESERVE, prior), prior)
        with self.assertRaisesRegex(ValueError, 'differs from the verified archive'):
            select(self.shards, 'cd' * 32, 100 * LINUX_RESERVE, LINUX_RESERVE, BACKING_RESERVE, prior)
        with self.assertRaisesRegex(ValueError, 'below its disk reserve'):
            select(self.shards, self.index, 100 * LINUX_RESERVE, LINUX_RESERVE, BACKING_RESERVE - 1, prior)


if __name__ == '__main__':
    unittest.main()
