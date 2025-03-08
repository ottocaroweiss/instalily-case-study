from agents.tests.validation_agent import ValidationAgent
from agents.main_agent import MainAgent


TEST_FILE = "agents/tests/test-cases.json"
ALLIGNMENT_FILE = "agents/tests/test_alignment.json"
if __name__ == "__main__":
    # Run the tests
    evaluator = ValidationAgent()
    evaluator.run_test_cases_for_agent_parallel(MainAgent, ALLIGNMENT_FILE, num_runs=1, max_workers=10)
    # evaluator.run_test_cases_for_agent_parallel(MainAgent, TEST_FILE, num_runs=1, max_workers=10)