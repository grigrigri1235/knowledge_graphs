import sys, unittest
sys.dont_write_bytecode = True
sys.path.insert(0, "/home/azureuser/code_projects/predicate_correctness")
from tests import test_v3_run_online as T
names = ["TestTasksFile.test_sha256_and_counts", "TestTasksFile.test_no_test_group_task_and_labels_match",
         "TestTasksFile.test_val_block_first_both_domains_interleaved", "TestTasksFile.test_fresh_build_equals_the_file",
         "TestSelectTasks", "TestUnits", "TestGroupPool", "TestTinyMeter", "TestRefusalsBeforeTheRunner"]
suite = unittest.defaultTestLoader.loadTestsFromNames(names, T)
r = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
sys.exit(0 if r.wasSuccessful() else 1)
