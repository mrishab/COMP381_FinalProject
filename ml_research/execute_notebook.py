"""Executes RealEstateDeals_Enhanced.ipynb and populates execution counts and outputs."""

import contextlib
import io
import json
import os
import sys

NOTEBOOK_PATH = "/workspace/RealEstateDeals_Enhanced.ipynb"


def run_notebook():
    if not os.path.exists(NOTEBOOK_PATH):
        raise FileNotFoundError(f"Notebook not found at {NOTEBOOK_PATH}")

    with open(NOTEBOOK_PATH, "r", encoding="utf-8") as f:
        nb = json.load(f)

    # Execution namespace
    exec_globals = {
        "__name__": "__main__",
        "__file__": NOTEBOOK_PATH,
    }
    # Ensure workspace root and ml_research are on sys.path
    if "/workspace" not in sys.path:
        sys.path.insert(0, "/workspace")
    if "/workspace/ml_research" not in sys.path:
        sys.path.insert(0, "/workspace/ml_research")

    exec_count = 1
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") == "code":
            source_lines = cell.get("source", [])
            code = "".join(source_lines)
            print(f"Executing Cell {i} (Code)...")

            stdout_buffer = io.StringIO()
            stderr_buffer = io.StringIO()

            try:
                with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
                    exec(code, exec_globals)
                
                output_text = stdout_buffer.getvalue()
                err_text = stderr_buffer.getvalue()

                cell["execution_count"] = exec_count
                cell["outputs"] = []

                if output_text:
                    cell["outputs"].append({
                        "name": "stdout",
                        "output_type": "stream",
                        "text": output_text.splitlines(keepends=True),
                    })
                if err_text:
                    cell["outputs"].append({
                        "name": "stderr",
                        "output_type": "stream",
                        "text": err_text.splitlines(keepends=True),
                    })
                print(f"Cell {i} completed. Output length: {len(output_text)} chars")
            except Exception as e:
                print(f"Cell {i} failed: {e}")
                cell["execution_count"] = exec_count
                cell["outputs"] = [{
                    "ename": type(e).__name__,
                    "evalue": str(e),
                    "output_type": "error",
                    "traceback": [f"Error in cell {i}: {e}"],
                }]
                raise

            exec_count += 1

    with open(NOTEBOOK_PATH, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2)

    print(f"Successfully executed and updated {NOTEBOOK_PATH} with {exec_count - 1} code outputs.")


if __name__ == "__main__":
    run_notebook()
