import os
import pandas as pd
import re
import datetime
import time
import subprocess
import argparse
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('--trace_dir', help='path to trace directory', required=True)
parser.add_argument('--results_dir', help='path to results directory', required=True)

args = parser.parse_args()
trace_dir = Path(args.trace_dir)
results_dir = Path(args.results_dir)


def get_trace_paths(start_path):
    ret_list = []
    for root, dirs, files in os.walk(start_path):
        for my_file in files:
            if my_file.endswith('_trace.gz'):
                ret_list.append(Path(root) / my_file)  # patch: use Path instead of raw string paths
    return ret_list


def process_run_op(pass_status, my_trace_path, my_run_name, op_file):
    run_name_split = my_run_name.split("/")  # my_run_name is deliberately built with "/"
    wl_name = run_name_split[0]
    run_name = run_name_split[1]

    print(f'Extracting data from : {op_file} |  WL:{wl_name} | Run:{run_name}')
    exec_time = 0

    _Instr = 0
    _Cycles = 0
    _IPC = 0
    _NumBr = 0
    _MispBr = 0
    _BrPerCyc = 0
    _MispBrPerCyc = 0
    _MR = 0
    _MPKI = 0
    _CycWP = 0
    _CycWPAvg = 0
    _CycWPPKI = 0

    _50PercInstr = 0
    _50PercCycles = 0
    _50PercIPC = 0
    _50PercNumBr = 0
    _50PercMispBr = 0
    _50PercBrPerCyc = 0
    _50PercMispBrPerCyc = 0
    _50PercMR = 0
    _50PercMPKI = 0
    _50PercCycWP = 0
    _50PercCycWPAvg = 0
    _50PercCycWPPKI = 0

    # patch: original used undefined variable trace_path
    trace_size = os.path.getsize(my_trace_path) / (1024 * 1024)

    pass_status_str = 'Fail'

    process_50perc_section = False
    process_100perc_section = False

    _50perc_section_header = 'DIRECT CONDITIONAL BRANCH PREDICTION MEASUREMENTS (50 Perc instructions)'
    _100perc_section_header = 'DIRECT CONDITIONAL BRANCH PREDICTION MEASUREMENTS (Full Simulation i.e. Counts Not Reset When Warmup Ends)'

    found_50perc_line_to_process = False
    found_100perc_line_to_process = False

    if pass_status:
        pass_status_str = 'Pass'
        with open(op_file, "r") as text_file:
            for line in text_file:
                if not line.strip():
                    continue

                if 'ExecTime' in line:
                    exec_time = line.strip().split()[-1]

                if not process_50perc_section and _50perc_section_header in line:
                    process_50perc_section = True
                    process_100perc_section = False

                if not process_100perc_section and _100perc_section_header in line:
                    process_50perc_section = False
                    process_100perc_section = True

                if process_50perc_section:
                    if found_50perc_line_to_process:
                        curr_split_line = line.split()
                        _50PercInstr = curr_split_line[0]
                        _50PercCycles = curr_split_line[1]
                        _50PercIPC = curr_split_line[2]
                        _50PercNumBr = curr_split_line[3]
                        _50PercMispBr = curr_split_line[4]
                        _50PercBrPerCyc = curr_split_line[5]
                        _50PercMispBrPerCyc = curr_split_line[6]
                        _50PercMR = curr_split_line[7]
                        _50PercMPKI = curr_split_line[8]
                        _50PercCycWP = curr_split_line[9]
                        _50PercCycWPAvg = curr_split_line[10]
                        _50PercCycWPPKI = curr_split_line[11]
                        process_50perc_section = False
                        found_50perc_line_to_process = False

                    if all(x in line for x in [
                        'Instr', 'Cycles', 'IPC', 'NumBr', 'MispBr',
                        'BrPerCyc', 'MispBrPerCyc', 'MR', 'MPKI',
                        'CycWP', 'CycWPAvg'
                    ]):
                        found_50perc_line_to_process = True

                if process_100perc_section:
                    if found_100perc_line_to_process:
                        curr_split_line = line.split()
                        _Instr = curr_split_line[0]
                        _Cycles = curr_split_line[1]
                        _IPC = curr_split_line[2]
                        _NumBr = curr_split_line[3]
                        _MispBr = curr_split_line[4]
                        _BrPerCyc = curr_split_line[5]
                        _MispBrPerCyc = curr_split_line[6]
                        _MR = curr_split_line[7]
                        _MPKI = curr_split_line[8]
                        _CycWP = curr_split_line[9]
                        _CycWPAvg = curr_split_line[10]
                        _CycWPPKI = curr_split_line[11]
                        process_100perc_section = False
                        found_100perc_line_to_process = False

                    if all(x in line for x in [
                        'Instr', 'Cycles', 'IPC', 'NumBr', 'MispBr',
                        'BrPerCyc', 'MispBrPerCyc', 'MR', 'MPKI',
                        'CycWP', 'CycWPAvg'
                    ]):
                        found_100perc_line_to_process = True

    retval = {
        'Workload': wl_name,
        'Run': run_name,
        'TraceSize': trace_size,
        'Status': pass_status_str,
        'ExecTime': exec_time,

        'Instr': _Instr,
        'Cycles': _Cycles,
        'IPC': _IPC,
        'NumBr': _NumBr,
        'MispBr': _MispBr,
        'BrPerCyc': _BrPerCyc,
        'MispBrPerCyc': _MispBrPerCyc,
        'MR': _MR,
        'MPKI': _MPKI,
        'CycWP': _CycWP,
        'CycWPAvg': _CycWPAvg,
        'CycWPPKI': _CycWPPKI,

        '50PercInstr': _50PercInstr,
        '50PercCycles': _50PercCycles,
        '50PercIPC': _50PercIPC,
        '50PercNumBr': _50PercNumBr,
        '50PercMispBr': _50PercMispBr,
        '50PercBrPerCyc': _50PercBrPerCyc,
        '50PercMispBrPerCyc': _50PercMispBrPerCyc,
        '50PercMR': _50PercMR,
        '50PercMPKI': _50PercMPKI,
        '50PercCycWP': _50PercCycWP,
        '50PercCycWPAvg': _50PercCycWPAvg,
        '50PercCycWPPKI': _50PercCycWPPKI,
    }
    return retval


my_traces = get_trace_paths(trace_dir)

print(f'Got {len(my_traces)} traces')

timestamp = datetime.datetime.now().strftime("%m_%d_%H-%M-%S")
results_dir.mkdir(parents=True, exist_ok=True)


def execute_trace(my_trace_path):
    my_trace_path = Path(my_trace_path)
    assert my_trace_path.exists()

    # patch: use pathlib instead of splitting on "/" so this works on windows too
    my_wl = my_trace_path.parent.name
    run_name = my_trace_path.name.removesuffix(".gz")

    wl_results_dir = results_dir / my_wl
    wl_results_dir.mkdir(parents=True, exist_ok=True)

    do_process = True
    my_run_name = f'{my_wl}/{run_name}'

    # patch: use cbp.exe on windows if present, otherwise cbp
    exe = Path("cbp.exe")
    if not exe.exists():
        exe = Path("cbp")

    # patch: use argument list and shell=False.
    exec_cmd = [str(exe.resolve()), str(my_trace_path.resolve())]

    op_file = wl_results_dir / f'{run_name}.log'

    if op_file.exists():
        do_process = False

    pass_status = True
    if do_process:
        print(f'Begin processing run:{my_run_name}')
        try:
            begin_time = time.time()
            run_op = subprocess.check_output(
                exec_cmd,
                shell=False,              # patch: do not use cmd.exe shell
                text=True,
                stderr=subprocess.STDOUT   # patch: capture simulator errors in log/output
            )
            end_time = time.time()
            exec_time = end_time - begin_time

            with open(op_file, "w") as text_file:
                print(f"CMD:{' '.join(exec_cmd)}", file=text_file)
                print(f"{run_op}", file=text_file)
                print(f"ExecTime = {exec_time}", file=text_file)

        except subprocess.CalledProcessError as e:
            print(f'Run: {my_run_name} failed')
            with open(op_file, "w") as text_file:
                print(f"CMD:{' '.join(exec_cmd)}", file=text_file)
                print(e.output, file=text_file)
            pass_status = False

        except Exception as e:
            print(f'Run: {my_run_name} failed: {e}')
            with open(op_file, "w") as text_file:
                print(f"CMD:{' '.join(exec_cmd)}", file=text_file)
                print(f"Exception: {e}", file=text_file)
            pass_status = False

    return pass_status, my_trace_path, op_file, my_run_name


if __name__ == '__main__':
    # patch: run serially by default.
    results = []
    for my_trace in my_traces:
        results.append(execute_trace(my_trace))

    # Original parallel version
    #
    # import multiprocessing as mp
    # with mp.Pool() as pool:
    #     results = pool.map(execute_trace, my_traces)

    df = pd.DataFrame(columns=[
        'Workload', 'Run', 'TraceSize', 'ExecTime',
        'Instr', 'Cycles', 'IPC', 'NumBr', 'MispBr',
        'BrPerCyc', 'MispBrPerCyc', 'MR', 'MPKI',
        'CycWP', 'CycWPAvg', 'CycWPPKI',
        '50PercInstr', '50PercCycles', '50PercIPC',
        '50PercNumBr', '50PercMispBr',
        '50PercBrPerCyc', '50PercMispBrPerCyc',
        '50PercMR', '50PercMPKI',
        '50PercCycWP', '50PercCycWPAvg', '50PercCycWPPKI'
    ])

    for my_result in results:
        pass_status = my_result[0]
        trace_path = my_result[1]
        op_file = my_result[2]
        my_run_name = my_result[3]

        run_dict = process_run_op(pass_status, trace_path, my_run_name, op_file)
        my_df = pd.DataFrame([run_dict])

        if not df.empty:
            df = pd.concat([df, my_df], ignore_index=True)
        else:
            df = my_df.copy()

    print(df)

    df.to_csv(results_dir / 'results.csv', index=False)

    unique_wls = df['Workload'].unique()

    print('\n\n----------------------------------Aggregate Metrics Per Workload Category----------------------------------\n')
    for my_wl in unique_wls:
        my_wl_br_misp_pki_amean = df[df['Workload'] == my_wl]['50PercMPKI'].astype(float).mean()
        my_wl_cyc_wp_pki_amean = df[df['Workload'] == my_wl]['50PercCycWPPKI'].astype(float).mean()

        print(f'WL:{my_wl:<10} Branch Misprediction PKI(BrMisPKI) AMean : {my_wl_br_misp_pki_amean}')
        print(f'WL:{my_wl:<10} Cycles On Wrong-Path PKI(CycWpPKI) AMean : {my_wl_cyc_wp_pki_amean}')

    print('-----------------------------------------------------------------------------------------------------------')

    br_misp_pki_amean = df['50PercMPKI'].astype(float).mean()
    cyc_wp_pki_amean = df['50PercCycWPPKI'].astype(float).mean()

    print('\n\n---------------------------------------------Aggregate Metrics---------------------------------------------\n')
    print(f'Branch Misprediction PKI(BrMisPKI) AMean : {br_misp_pki_amean}')
    print(f'Cycles On Wrong-Path PKI(CycWpPKI) AMean : {cyc_wp_pki_amean}')
    print('-----------------------------------------------------------------------------------------------------------')