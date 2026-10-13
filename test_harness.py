import os
import subprocess
import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

NUM_PARALLEL = 32
RUNLIST = "test_runlist.txt" # traces should be located in training_traces/
STATS_TO_COLLECT = [
    "Integrated Predictor MPKI", # this is the MPKI of the predictor thats actually connected the simulator, ie MPKI of the predictor returned by get_cond_dir_prediction(). Currently this is the 8KB 2016 TAGE-SC-L/
    "TM MPKI",
    "GShare MPKI"
]

OUTFILE = "run_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".csv"

if os.name == "nt":
    CBP_EXECUTABLE = "./cbp.exe"
else:
    CBP_EXECUTABLE = "./cbp"


def get_traces():
    trace_names = []

    for trace_name in open(RUNLIST):
        trace_name = trace_name.strip()

        if (trace_name != ""):
            trace_names.append(trace_name)

    return trace_names


def run_trace(trace_name):
    stats = {}

    trace_name = trace_name.strip() + ".gz"

    for folder, subfolders, files in os.walk("training_traces"):
        if trace_name in files:
            trace_path = os.path.join(folder, trace_name)
            break
    else:
        return trace_name, None

    print("running test on " + trace_path)

    result = subprocess.run(
        [CBP_EXECUTABLE, "-E", "1000000", trace_path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    for line in result.stdout.splitlines():
        fields = line.split()

        # capture mpki of predictor integrated with the simulator interface
        if len(fields) >= 5 and fields[0] == "CondDirect":
            stats["Integrated Predictor MPKI"] = float(fields[4])
            continue

        # capture manually printed predictor statistics
        for stat_name in STATS_TO_COLLECT:
            if line.startswith(stat_name + ":"):
                value = line.split(":")[-1].strip().replace("%", "")
                stats[stat_name] = float(value)

    return trace_name, stats

def run_tests(trace_names):
    results = {}

    with ThreadPoolExecutor(max_workers=NUM_PARALLEL) as executor:
        test_results = executor.map(run_trace, trace_names)

        for trace_name, stats in test_results:
            if stats is None:
                print(trace_name + ": failed")
                continue

            results[trace_name] = stats

            print(trace_name)
            for stat in STATS_TO_COLLECT:
                if stat in stats:
                    print("  " + stat + ": " + str(stats[stat]))
         

    return results

def dump_results(results):
    with open(OUTFILE, "w", newline="") as file:
        writer = csv.writer(file)

        writer.writerow(["trace_name"] + STATS_TO_COLLECT)

        for trace_name in results:
            row = [trace_name]

            for stat_name in STATS_TO_COLLECT:
                row.append(results[trace_name].get(stat_name, ""))

            writer.writerow(row)

    print("results written to " + OUTFILE)

if __name__ == "__main__":
    trace_names = get_traces()
    results = run_tests(trace_names)
    dump_results(results)



