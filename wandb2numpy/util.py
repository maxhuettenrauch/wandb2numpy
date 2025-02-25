import numpy as np
import pandas as pd
from collections import defaultdict
from tqdm import tqdm

try:
    from collections.abc import Mapping
except ImportError:
    from collections import Mapping


def nested_dict(dtype=list):
    return defaultdict(lambda: defaultdict(dtype))


# from https://stackoverflow.com/questions/26496831/how-to-convert-defaultdict-of-defaultdicts-of-defaultdicts-to-dict-of-dicts-o
def default_to_regular(d):
    if isinstance(d, defaultdict):
        d = {k: default_to_regular(v) for k, v in d.items()}
    return d


def extract_data(run, fields, config):
    max_samples = 12000
    
    if fields == "all" or fields == ["all"]:
        # get history with only 1 sample, to extract all available field names
        dummy_history_all_fields = run.history(samples = 1, pandas=False)
        if list(dummy_history_all_fields): # check that history is not empty
            all_fields_list = list(dummy_history_all_fields[0].keys())
            # remove fields that are automatically logged by wandb
            if "_step" in all_fields_list: all_fields_list.remove("_step")
            if "_runtime" in all_fields_list: all_fields_list.remove("_runtime")
            if "_timestamp" in all_fields_list: all_fields_list.remove("_timestamp")
        else: 
            all_fields_list = []
            tqdm.write("Warning: Current run contains no fields at all.")
        
        fields = all_fields_list

    if 'history_samples' in config.keys():
        if config['history_samples'] == "all":
            history = run.scan_history()
        else:
            if not isinstance(config['history_samples'], int):
                tqdm.write(f"Error: history_samples must be 'all' or of type Integer")
                history = []
            else:
                n_samples = min(config['history_samples'], max_samples)
                history = run.history(keys=fields, samples=n_samples, pandas=False)
    else:
        history = run.history(keys=fields, samples=max_samples, pandas=False)

    data_dict = {}
    for key in fields:
        data_list = []
        is_valid_key = True
        for data_point in history:
            if not key in data_point.keys():
                tqdm.write(f"Warning: Run {run.name} does not have a field called {key}")
                is_valid_key = False
                break
            if is_valid_key:
                data_list.append(data_point[key])
        data_dict[key] = np.array(data_list)
    return data_dict


def run_dict_to_field_dict(run_dict, config, padding_method):
    n_runs = len(run_dict)
    output_dict = {}
    all_fields = set()
    for x in list(run_dict.keys()):
        all_fields.update(list(run_dict[x].keys()))

    for field in all_fields:
        non_empty_runs = [run_dict[i][field] for i in range(n_runs) if field in run_dict[i].keys() and len(run_dict[i][field]) != 0 and not isinstance(run_dict[i][field][0], dict)]
        n_non_empty_runs = len(non_empty_runs)
        if n_non_empty_runs > 0:
            max_steps = max([len(run) for run in non_empty_runs])
        else:
            max_steps = 0
        
        print(f"Number of runs that include field {field}: {n_non_empty_runs}")
        output_array = np.zeros((n_non_empty_runs, max_steps))
        for k, run in enumerate(non_empty_runs):
            steps = run.shape[0]
            if steps == max_steps: # check if array has length max_steps, otherwise pad to that size with NaNs (in the end)
                output_array[k] = run
            else:
                output_array[k] = pad_run(run, max_steps, padding_method)
        if "output_data_type" in config.keys() and config["output_data_type"] == "csv":
            row_names = [f"run {i}" for i in range(0, output_array.shape[0])]
            column_names = [f"step {i}" for i in range(0, output_array.shape[1])]
            df = pd.DataFrame(output_array, index = row_names, columns = column_names)
            output_dict[field] = df
        else:
            output_dict[field] = output_array
    return output_dict


def pad_run(array, max_steps, method='nan'):
    steps = array.shape[0]
    if method == 'nan':
        pad_value = np.nan
    elif method == 'last':
        pad_value = array[-1]
    else:
        raise ValueError(f'Unknown padding method {method}')
    print(f"Warning: Run has {max_steps - steps} steps less than longest run, padding array with NaNs")
    return np.pad(array.astype('float64'), (0, max_steps - steps), 'constant', constant_values=pad_value)


def deep_update(base_dict: dict, update_dict: dict) -> dict:
    """Updates the base dictionary with corresponding values from the update dictionary, including nested collections.
       Not updated values are kept as is.
    Arguments:
        base_dict {dict} -- dictionary to be updated
        update_dict {dict} -- dictianry holding update values
    Returns:
        dict -- dictanry with updated values
    """
    for key, value in update_dict.items():
        # Update Recursively
        if isinstance(value, Mapping):
            branch = deep_update(base_dict.get(key, {}), value)
            base_dict[key] = branch
        else:
            base_dict[key] = update_dict[key]
    return base_dict


def filter_match(config, filter_param, run_param):
    if not filter_param in config.keys():
        return True
    elif config[filter_param] == "all":
        return True
    else:
        return run_param in config[filter_param]