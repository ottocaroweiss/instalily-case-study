# validation_agent_deepseek.py

# FOR REFERENCE: This is the ValidationAgent class that uses DeepSeek to evaluate responses.
# It's used to validate the responses of an agent against a set of test cases.

import json
import os
from typing import Union, List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv
load_dotenv()
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

llm_deepseek = ChatDeepSeek(
    model="deepseek-chat",
    max_retries=2,
    api_key=DEEPSEEK_API_KEY
)
class ValidationAgent:
    """
    ValidationAgent that:
      1) Loads test cases from JSON
      2) Runs them on an interpreter or agent
      3) Uses DeepSeek to evaluate if the response meets the 'valid_description'
         by returning 'PASSED' or 'FAILED'.
      4) Prints a summary of pass/fail plus only the debug details for fails.

    JSON structure example:
    {
      "TestSuiteName": [
        {
          "prompts": ["User line 1", "User line 2", ...],
          "valid_description": "A single string or an array describing correct response"
        },
        ...
      ]
    }
    """

    def __init__(self):
        # This is a system-level instruction to the DeepSeek LLM on how to evaluate
        self.system_prompt = (
            "You are an evaluator of LLM agents. You are always given:\n"
            "1) [Text from an LLM Agent-User Interaction]\n"
            "2) [Description of a valid response.]\n\n"
            "You must evaluate if the system's response meets the valid description.\n\n"
            "Answer ONLY 'PASSED' or 'FAILED' (all caps).\n"
            "If the system's response fully satisfies the valid description, respond 'PASSED', else 'FAILED'."
        )

    # ---------------------------------------------------------------
    # PUBLIC METHODS: Each top-level function uses _report_results
    # ---------------------------------------------------------------
    def run_test_cases_for_interpreter(self, test_json_path: str, num_runs: int = 1):
        """
        Reads test cases from `test_json_path`, runs them on a
        simple "interpreter" approach, and accumulates pass/fail results.

        The final debug for any failures is printed at the end.
        """
        with open(test_json_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        suite_results = {}
        suite_debug = {}  # suiteName -> list of debug data (or None) for each test

        for suite_name, test_list in test_data.items():
            pass_fail_list = []
            debug_list = [None]*len(test_list)

            for idx, test_case in enumerate(test_list):
                success_count = 0
                debug_text_acc = []
                for _ in range(num_runs):
                    response = self._run_interpreter(test_case["prompts"])
                    passed, debug_info = self._check_response_deepseek(
                        response, 
                        test_case["valid_description"]
                    )
                    debug_text_acc.append(debug_info)
                    if passed:
                        success_count += 1

                # Strict pass => all runs pass
                test_pass = (success_count == num_runs)
                pass_fail_list.append(test_pass)

                # If it fails, store the debug of the last run, for instance
                if not test_pass:
                    debug_list[idx] = "\n---\n".join(debug_text_acc)

            suite_results[suite_name] = pass_fail_list
            suite_debug[suite_name] = debug_list

        self._report_results(suite_results, suite_debug)

    def run_test_cases_for_agent(self, agent, test_json_path: str, num_runs: int = 1):
        """
        Reads test cases, uses the given 'agent' object to handle queries,
        validates results, prints summary + failures' debug info.
        """
        with open(test_json_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        suite_results = {}
        suite_debug = {}

        for suite_name, test_list in test_data.items():
            pass_fail_list = []
            debug_list = [None]*len(test_list)

            for idx, test_case in enumerate(test_list):
                success_count = 0
                debug_text_acc = []
                for _ in range(num_runs):
                    response = self._run_agent_interaction(agent, test_case["prompts"])
                    passed, debug_info = self._check_response_deepseek(
                        response,
                        test_case["valid_description"]
                    )
                    debug_text_acc.append(debug_info)
                    if passed:
                        success_count += 1

                test_pass = (success_count == num_runs)
                pass_fail_list.append(test_pass)
                if not test_pass:
                    # store debug from last attempt or all attempts
                    debug_list[idx] = "\n---\n".join(debug_text_acc)

            suite_results[suite_name] = pass_fail_list
            suite_debug[suite_name] = debug_list

        self._report_results(suite_results, suite_debug)

    def run_test_cases_for_agent_parallel(self, agent_class, test_json_path: str, num_runs: int = 1, max_workers: int = 10):
        """
        Example of parallel execution of each test with a fresh agent instance.
        We'll store debug info for fails and print them at the end.
        """
        with open(test_json_path, "r", encoding="utf-8") as f:
            test_data = json.load(f)

        suite_results = {}
        suite_debug = {}

        for suite_name, test_list in test_data.items():
            pass_fail_list = [False]*len(test_list)
            debug_list = [None]*len(test_list)

            def run_one_test(idx: int):
                test_case = test_list[idx]
                success_count = 0
                debug_text_acc = []
                for _ in range(num_runs):
                    # new agent each time
                    agent = agent_class()
                    response = self._run_agent_interaction(agent, test_case["prompts"])
                    passed, debug_info = self._check_response_deepseek(
                        user_prompts=test_case["prompts"],
                        response=response,
                        valid_desc=test_case["valid_description"]
                    )
                    debug_text_acc.append(debug_info)
                    if passed:
                        success_count += 1

                return (idx, success_count == num_runs, "\n---\n".join(debug_text_acc))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(run_one_test, i) for i in range(len(test_list))]
                for fut in as_completed(futures):
                    idx, pass_bool, debug_txt = fut.result()
                    pass_fail_list[idx] = pass_bool
                    if not pass_bool:
                        debug_list[idx] = debug_txt

            suite_results[suite_name] = pass_fail_list
            suite_debug[suite_name] = debug_list

        self._report_results(suite_results, suite_debug)

    # ------------------------------------------------------
    # Internal run methods
    # ------------------------------------------------------
    def _run_interpreter(self, prompts: List[str]) -> str:
        # Combine prompts as a single user_input
        user_input = "\n".join(prompts)
        return f"[MOCK INTERPRETER] replying to: {user_input}"

    def _run_agent_interaction(self, agent, prompts: List[str]) -> str:
        final_response = ""
        for p in prompts:
            final_response = agent.run(p)
        return final_response

    # ------------------------------------------------------
    # LLM-based check of the agent/chain response
    # ------------------------------------------------------
    def _check_response_deepseek(
        self,
        user_prompts: List[str],
        response: str,
        valid_desc: Union[str, List[str]]
    ) -> Tuple[bool, str]:
        """
        Evaluates whether 'response' satisfies 'valid_desc'.
        Also includes the original user prompts in the debug info.
        Returns (isPassed, debug_info).
        """
        if isinstance(valid_desc, list):
            valid_desc_str = "\n".join(valid_desc)
        else:
            valid_desc_str = valid_desc

        # Show user conversation in debug
        user_prompt_text = "\n".join(user_prompts)

        # We'll pass a single user message to DeepSeek that includes:
        # - The agent's final response
        # - The valid desc
        # and instructions to respond ONLY PASSED/FAILED
        user_message = (
            f"System's response:\n{response}\n\n"
            f"Valid description:\n{valid_desc_str}\n\n"
            "Answer ONLY 'PASSED' or 'FAILED' (all caps)."
        )

        messages = [
            ("system", self.system_prompt),
            ("human", user_message),
        ]

        result = llm_deepseek.invoke(messages)
        verdict_raw = result.content.strip()
        verdict = verdict_raw.upper()

        # Build debug info
        debug_info = (
            "======== Failed Test ========\n"
            f"[User prompts]:\n{user_prompt_text}\n\n"
            f"[System's final response]:\n{response}\n\n"
            f"[Valid desc]:\n{valid_desc_str}\n\n"
            f"[DeepSeek verdict]: {verdict_raw}\n"
            "=============================\n"
        )

        return (verdict == "PASSED", debug_info)


    # ------------------------------------------------------
    # Summaries
    # ------------------------------------------------------
    def _report_results(self, suite_results: Dict[str, List[bool]], suite_debug: Dict[str, List[Union[str, None]]]):
        """
        Summarize pass/fail for each suite and overall,
        sorted from highest fail to lowest fail.
        Then print the debug info for each failed test.

        suite_results: suiteName -> list[bool] pass/fails
        suite_debug:   suiteName -> list[str|None] debug info or None for each test
        """
        total_tests = 0
        total_passed = 0
        fails_per_suite = {}

        # We'll also store the fails details in memory
        fail_details = {}  # suiteName -> list of debug strings

        for suite_name, pass_list in suite_results.items():
            suite_total = len(pass_list)
            suite_passed = sum(1 for x in pass_list if x)
            suite_fails = suite_total - suite_passed

            total_tests += suite_total
            total_passed += suite_passed
            fails_per_suite[suite_name] = suite_fails

            # Gather debug info for fails
            debug_list = suite_debug[suite_name]
            # If pass_list[i] is false => we store debug_list[i]
            suite_fail_debugs = []
            for i, passed in enumerate(pass_list):
                if not passed:
                    suite_fail_debugs.append(debug_list[i])

            fail_details[suite_name] = suite_fail_debugs

        if total_tests == 0:
            print("No tests run.")
            return

        pass_percent = (total_passed / total_tests) * 100.0
        # Sort by # fails desc
        sorted_fails = sorted(fails_per_suite.items(), key=lambda x: x[1], reverse=True)

        print("\n=================== Validation Results =====================")
        print(f"Overall pass percentage: {pass_percent:.1f}%\n")
        for suite_name, fail_count in sorted_fails:
            print(f"{suite_name}: {fail_count} failures")
        print("===========================================================\n")

        # Now print the debug info for fails
        for suite_name, fail_count in sorted_fails:
            if fail_count == 0:
                continue
            print(f"--- {suite_name} FAILURES ({fail_count}) ---")
            for debug_str in fail_details[suite_name]:
                print(debug_str)  # Each debug_str is the LLM interaction etc.
            print("\n")
