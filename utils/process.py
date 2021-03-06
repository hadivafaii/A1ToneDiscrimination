import h5py
import argparse
from scipy.stats import zscore
from prettytable import PrettyTable
from collections import Counter
from .generic_utils import *
import matplotlib.pyplot as plt
import seaborn as sns
sns.set_style('darkgrid')


def bag_of_neurons(
        h_load_file: str,
        trials: List[str] = None,
        freqs: List[str] = None,):

    trials = ['hit', 'miss', 'correctreject', 'falsealarm'] if trials is None else trials
    freqs = [7000, 9899, 14000, 19799] if freqs is None else freqs

    l2i = {trial: i for i, trial in enumerate(trials)}
    i2l = {i: lbl for lbl, i in l2i.items()}

    f2i = {freq: i for i, freq in enumerate(freqs)}
    i2f = {i: freq for freq, i in f2i.items()}

    dff_trial = []
    dff_freq = []
    df_trial = pd.DataFrame()
    df_freq = pd.DataFrame()

    f = h5py.File(h_load_file, 'r')
    for name in f:
        behavior = f[name]['behavior']
        passive = f[name]['passive']

        good_cells_b = np.array(behavior["good_cells"], dtype=int)
        good_cells_p = np.array(passive["good_cells"], dtype=int)
        good_cells = set(good_cells_b).intersection(set(good_cells_p))
        good_cells = sorted(list(good_cells))

        stimfrequency = np.array(behavior['trial_info']['stimfrequency'], dtype=int)
        dff = np.array(behavior['dff'], dtype=float)[..., good_cells]
        nt, _, nc = dff.shape

        for trial in trials:
            indxs = np.where(np.array(behavior['trial_info'][trial]) == 1)[0]
            dff_trial.append(dff[:, indxs, :].reshape(nt, -1))

            cell_indx = np.expand_dims(range(nc), 0)
            cell_indx = np.repeat(cell_indx, len(indxs), axis=0)

            data_dict = {
                'cell_indx': cell_indx.flatten(),
                'trial': [trial] * len(indxs) * nc,
                'name': [name] * len(indxs) * nc,
            }
            df_trial = pd.concat([df_trial, pd.DataFrame.from_dict(data_dict)])

        for freq in freqs:
            indxs = np.where(stimfrequency == freq)[0]
            dff_freq.append(dff[:, indxs, :].reshape(nt, -1))

            cell_indx = np.expand_dims(range(nc), 0)
            cell_indx = np.repeat(cell_indx, len(indxs), axis=0)

            data_dict = {
                'cell_indx': cell_indx.flatten(),
                'freq': [freq] * len(indxs) * nc,
                'name': [name] * len(indxs) * nc,
            }
            df_freq = pd.concat([df_freq, pd.DataFrame.from_dict(data_dict)])
    f.close()

    dff = np.concatenate(dff_trial, axis=-1).T
    df = reset_df(df_trial)
    tst_, trn_ = train_test_split(x=dff, labels=df.trial)
    output_trial = {
        'dff': dff,
        'df': df,
        'str2int': l2i,
        'int2str': i2l,
        'tst_indxs': tst_,
        'trn_indxs': trn_,
    }
    dff = np.concatenate(dff_freq, axis=-1).T
    df = reset_df(df_freq)
    tst_, trn_ = train_test_split(x=dff, labels=df.freq)
    output_freq = {
        'dff': dff,
        'df': df,
        'str2int': f2i,
        'int2str': i2f,
        'tst_indxs': tst_,
        'trn_indxs': trn_,
    }
    return output_trial, output_freq


def combine_dfs(load_dir: str) -> pd.DataFrame:
    df_all = []
    for file_name in tqdm(os.listdir(load_dir)):
        with open(pjoin(load_dir, file_name)) as f:
            df = pd.read_pickle(f.name)
            df_all.append(df)
    df_all = pd.concat(df_all)
    return reset_df(df_all)


def summarize_data(load_file: str, verbose: bool = True, save_file: str = None):
    all_trial_types = [
        'correctreject', 'early', 'earlyfalsealarm', 'earlyhit', 'falsealarm', 'hit', 'miss']
    stim_info_types = ['stimfrequency', 'stimlevel']

    base_cols = ['Date', 'Subject Name', 'Good Cells', 'Num Trials']

    t_behavior_detailed = PrettyTable(base_cols + all_trial_types + stim_info_types)
    t_passive_detailed = PrettyTable(base_cols + stim_info_types)

    tot_expts = 0
    tot_good_cells = 0
    tot_behavior_trials = 0
    tot_passive_trials = 0
    animal_names_all = []
    trial_types_counter = Counter()
    behavior_frequencies_counter = Counter()
    passive_frequencies_counter = Counter()
    behavior_stimlevel_counter = Counter()
    passive_stimlevel_counter = Counter()

    h5py_file = h5py.File(load_file, "r")
    for expt in h5py_file:
        tot_expts += 1

        animal_name, date = expt.split('_')
        animal_names_all.append(animal_name)

        behavior = h5py_file[expt]['behavior']
        passive = h5py_file[expt]['passive']

        nb_good_neurons = min(len(list(behavior['good_cells'])), len(list(passive['good_cells'])))
        tot_good_cells += nb_good_neurons

        behavior_nb_trials = behavior['dff'].shape[1]
        passive_nb_trials = passive['dff'].shape[1]

        tot_behavior_trials += behavior_nb_trials
        tot_passive_trials += passive_nb_trials

        base_row = [date, animal_name, nb_good_neurons]

        # behavior
        row = base_row + [behavior_nb_trials]

        behavior_trial_info = behavior['trial_info']
        for k in all_trial_types:
            if k in behavior_trial_info.keys():
                num = sum(behavior_trial_info[k])
                tot = len(behavior_trial_info[k])
                row += ["{:d} ({:d} {:s})".format(num, int(np.rint(num / tot * 100)), "%")]
                trial_types_counter[k] += num
            else:
                row += ['']
        for k in stim_info_types:
            if k in behavior_trial_info.keys():
                x_list = list(np.unique(behavior_trial_info[k]))
                row.append(x_list) if len(x_list) > 1 else row.extend(x_list)
            else:
                row += ['']

        t_behavior_detailed.add_row(row)

        try:
            for freq in list(behavior_trial_info['stimfrequency']):
                behavior_frequencies_counter[freq] += 1
        except KeyError:
            continue
        try:
            for stim_lvl in list(behavior_trial_info['stimlevel']):
                behavior_stimlevel_counter[stim_lvl] += 1
        except KeyError:
            continue

        # passive
        row = base_row + [passive_nb_trials]

        passive_trial_info = passive['trial_info']
        for k in stim_info_types:
            if k in passive_trial_info.keys():
                x_list = list(np.unique(passive_trial_info[k]))
                row.append(x_list) if len(x_list) > 1 else row.extend(x_list)
            else:
                row += ['']

        t_passive_detailed.add_row(row)

        try:
            for freq in list(passive_trial_info['stimfrequency']):
                passive_frequencies_counter[freq] += 1
        except KeyError:
            continue
        try:
            for stim_lvl in list(passive_trial_info['stimlevel']):
                passive_stimlevel_counter[stim_lvl] += 1
        except KeyError:
            continue

    h5py_file.close()

    msg1 = "*** Data Summary ***\n"
    msg1 += '-' * 45
    msg1 += "\n- num experiments: {:d},\n- num animals: {:d},\n- num good cells: {:d},\
    \n- num behavior trials {:d},\n- num passive trials {:d},\
    \n\n- num/percent different trials:\n"

    msg1 = msg1.format(
        tot_expts, len(list(np.unique(animal_names_all))), tot_good_cells,
        tot_behavior_trials, tot_passive_trials)

    msg2 = ""
    for k, v in trial_types_counter.most_common():
        msg2 += "\t○ {:s}: {:d} ({:d}{:s})\n".format(k, v, int(np.rint(v / tot_behavior_trials * 100)), '%')
    msg2 += "\n- percent frequencies used (behavior):\n"

    msg3 = ""
    for k, v in sorted(behavior_frequencies_counter.most_common(), key=lambda x: x[0]):
        msg3 += "\t○ {:d} Hz: {:d}{:s}\n".format(k, int(np.ceil(v / tot_behavior_trials * 100)), '%')
    msg3 += "\n- percent frequencies used (passive):\n"

    msg4 = ""
    for k, v in sorted(passive_frequencies_counter.most_common(), key=lambda x: x[0]):
        msg4 += "\t○ {:d} Hz: {:d}{:s}\n".format(k, int(np.ceil(v / tot_passive_trials * 100)), '%')
    msg4 += "\n- percent stim levels used (behavior):\n"

    msg5 = ""
    for k, v in behavior_stimlevel_counter.most_common():
        msg5 += "\t○ {:d} dB: {:d}{:s}\n".format(k, int(np.ceil(v / tot_behavior_trials * 100)), '%')
    msg5 += "\n- percent stim levels used (passive):\n"

    msg6 = ""
    for k, v in passive_stimlevel_counter.most_common():
        msg6 += "\t○ {:d} dB: {:d}{:s}\n".format(k, int(np.ceil(v / tot_passive_trials * 100)), '%')
    msg6 += '-' * 45

    msg = msg1 + msg2 + msg3 + msg4 + msg5 + msg6

    if verbose:
        print(msg)

    if save_file is not None:
        save_dir = os.path.dirname(save_file)
        try:
            os.makedirs(save_dir, exist_ok=True)
        except FileNotFoundError:
            pass

        with open(save_file, 'w') as file:
            file.write(msg + '\n\n\n\n')

            msg = "*** Behavior (detailed) ***\n\n"
            file.write(msg)
            file.write(t_behavior_detailed.get_string())

            msg = "\n\n\n\n*** Passive (detailed) ***\n\n"
            file.write(msg)
            file.write(t_passive_detailed.get_string())

    summary_data = {
        'trial_types_counter': trial_types_counter,
        'behavior_frequencies_counter': behavior_frequencies_counter,
        'passive_frequencies_counter': passive_frequencies_counter,
        'behavior_stimlevel_counter': behavior_stimlevel_counter,
        'passive_stimlevel_counter': passive_stimlevel_counter,
    }
    return summary_data


def process_data(load_file: str, save_dir: str, normalize: bool = False):
    os.makedirs(save_dir, exist_ok=True)
    f = h5py.File(load_file, 'r')
    pbar = tqdm(f, dynamic_ncols=True)

    for name in pbar:
        pbar.set_description(name)
        behavior = f[name]['behavior']
        passive = f[name]['passive']

        good_cells_b = np.array(behavior["good_cells"], dtype=int)
        good_cells_p = np.array(passive["good_cells"], dtype=int)
        good_cells = set(good_cells_b).intersection(set(good_cells_p))
        good_cells = sorted(list(good_cells))

        # behavior
        targetlick = np.array(behavior['targetlick'], dtype=int)
        nontargetlick = np.array(behavior['nontargetlick'], dtype=int)
        lick = targetlick + nontargetlick

        dff_good = np.array(behavior['dff'], dtype=float)[:, :, good_cells]
        nt, _, nc = dff_good.shape

        stimfrequency = np.array(behavior['trial_info']['stimfrequency'], dtype=int)
        stimlevel = np.array(behavior['trial_info']['stimlevel'], dtype=int)

        if normalize:
            dff_good = zscore(dff_good)

        dictdata_list = []
        for k, v in behavior['trial_info'].items():
            trial_data = np.array(v, dtype=int)
            trial_size = sum(trial_data == 1)
            if not trial_size or 'target' in k:
                continue

            dff_ = dff_good[:, trial_data == 1, :]
            max_activation_list = []
            cell_tag_list = []
            for cell in range(nc):
                max_act = max(dff_[..., cell].mean(1), key=abs)
                max_activation_list.append(max_act)
                if max_act >= 0:
                    tag = "EXC"
                else:
                    tag = "SUP"
                cell_tag_list.append(tag)

            max_activations = np.expand_dims(max_activation_list, 0)
            max_activations = np.expand_dims(max_activations, 0)
            max_activations = np.repeat(max_activations, nt, axis=0)
            max_activations = np.repeat(max_activations, trial_size, axis=1)

            cell_tags = np.expand_dims(cell_tag_list, 0)
            cell_tags = np.expand_dims(cell_tags, 0)
            cell_tags = np.repeat(cell_tags, nt, axis=0)
            cell_tags = np.repeat(cell_tags, trial_size, axis=1)

            cell_indxs = np.expand_dims(np.arange(nc), 0)
            cell_indxs = np.expand_dims(cell_indxs, 0)
            cell_indxs = np.repeat(cell_indxs, nt, axis=0)
            cell_indxs = np.repeat(cell_indxs, trial_size, axis=1)

            time_points = np.expand_dims(np.arange(nt), -1)
            time_points = np.expand_dims(time_points, -1)
            time_points = np.repeat(time_points, trial_size, axis=1)
            time_points = np.repeat(time_points, nc, axis=-1)

            stimfrequency_ = np.expand_dims(stimfrequency[trial_data == 1], 0)
            stimfrequency_ = np.expand_dims(stimfrequency_, -1)
            stimfrequency_ = np.repeat(stimfrequency_, nt, axis=0)
            stimfrequency_ = np.repeat(stimfrequency_, nc, axis=-1)

            stimlevel_ = np.expand_dims(stimlevel[trial_data == 1], 0)
            stimlevel_ = np.expand_dims(stimlevel_, -1)
            stimlevel_ = np.repeat(stimlevel_, nt, axis=0)
            stimlevel_ = np.repeat(stimlevel_, nc, axis=-1)

            lick_ = lick[:, trial_data == 1]
            lick_ = np.expand_dims(lick_, axis=-1)
            lick_ = np.repeat(lick_, nc, axis=-1)

            data_dict = {
                "name": [name] * nt * trial_size * nc,
                "timepoint": time_points.flatten(),
                "cell_indx": cell_indxs.flatten(),
                "cell_tag": cell_tags.flatten(),
                "max_act": max_activations.flatten(),
                "trial": [k] * nt * trial_size * nc,
                "stimfreq": stimfrequency_.flatten(),
                "stimlevel": stimlevel_.flatten(),
                "dff": dff_.flatten(),
                "lick": lick_.flatten(),
            }
            dictdata_list.append(data_dict)

        # passive
        dff_good = np.array(passive['dff'], dtype=float)[:, :, good_cells]
        nt, _, nc = dff_good.shape

        stimfrequency = np.array(passive['trial_info']['stimfrequency'], dtype=int)
        stimlevel = np.array(passive['trial_info']['stimlevel'], dtype=int)

        for freq in sorted(np.unique(stimfrequency)):
            trial_size = sum(stimfrequency == freq)

            dff_ = dff_good[:, stimfrequency == freq, :]
            max_activation_list = []
            cell_tag_list = []
            for cell in range(nc):
                max_act = max(dff_[..., cell].mean(1), key=abs)
                max_activation_list.append(max_act)
                if max_act >= 0:
                    tag = "EXC"
                else:
                    tag = "SUP"
                cell_tag_list.append(tag)

            max_activations = np.expand_dims(max_activation_list, 0)
            max_activations = np.expand_dims(max_activations, 0)
            max_activations = np.repeat(max_activations, nt, axis=0)
            max_activations = np.repeat(max_activations, trial_size, axis=1)

            cell_tags = np.expand_dims(cell_tag_list, 0)
            cell_tags = np.expand_dims(cell_tags, 0)
            cell_tags = np.repeat(cell_tags, nt, axis=0)
            cell_tags = np.repeat(cell_tags, trial_size, axis=1)

            cell_indxs = np.expand_dims(np.arange(nc), 0)
            cell_indxs = np.expand_dims(cell_indxs, 0)
            cell_indxs = np.repeat(cell_indxs, nt, axis=0)
            cell_indxs = np.repeat(cell_indxs, trial_size, axis=1)

            time_points = np.expand_dims(np.arange(nt), -1)
            time_points = np.expand_dims(time_points, -1)
            time_points = np.repeat(time_points, trial_size, axis=1)
            time_points = np.repeat(time_points, nc, axis=-1)

            stimfrequency_ = np.expand_dims(stimfrequency[stimfrequency == freq], 0)
            stimfrequency_ = np.expand_dims(stimfrequency_, -1)
            stimfrequency_ = np.repeat(stimfrequency_, nt, axis=0)
            stimfrequency_ = np.repeat(stimfrequency_, nc, axis=-1)

            stimlevel_ = np.expand_dims(stimlevel[stimfrequency == freq], 0)
            stimlevel_ = np.expand_dims(stimlevel_, -1)
            stimlevel_ = np.repeat(stimlevel_, nt, axis=0)
            stimlevel_ = np.repeat(stimlevel_, nc, axis=-1)

            data_dict = {
                "name": [name] * nt * trial_size * nc,
                "timepoint": time_points.flatten(),
                "cell_indx": cell_indxs.flatten(),
                "cell_tag": cell_tags.flatten(),
                "max_act": max_activations.flatten(),
                "trial": ['passive'] * nt * trial_size * nc,
                "stimfreq": stimfrequency_.flatten(),
                "stimlevel": stimlevel_.flatten(),
                "dff": dff_.flatten(),
                "lick": [np.nan] * nt * trial_size * nc,
            }
            dictdata_list.append(data_dict)

        # make the final df
        df = pd.DataFrame.from_dict(merge_dicts(dictdata_list))
        save_obj(obj=df, file_name="{}.df".format(name), save_dir=save_dir, mode='df', verbose=True)
    f.close()
    print('[PROGRESS] processing done.')
    print('[PROGRESS] combining all dfs.')
    df_all = combine_dfs(load_dir=save_dir)
    save_obj(obj=df_all, file_name="all.df", save_dir=save_dir, mode='df', verbose=True)
    print('[PROGRESS] done.')


def organize_data(base_dir: str, nb_std: int = 1):
    data_dir = pjoin(base_dir, 'Data')
    processed_dir = pjoin(base_dir, 'python_processed')
    os.makedirs(processed_dir, exist_ok=True)
    file_name = "organized_nb_std={:d}.h5".format(nb_std)

    save_file = pjoin(processed_dir, file_name)
    if os.path.isfile(save_file):
        print('[INFO] file found. exiting...\n\n')
        return
    else:
        print('[INFO] file not found. organizing...\n\n')

    _corrupted_expts = ["ken_2016-09-30"]
    h5_file = h5py.File(save_file, 'w')
    for path in tqdm(Path(data_dir).rglob('*.pkl')):
        file = str(path)
        data = pickle.load(open(file, "rb"))
        name = "{:s}_{:s}".format(data[0]["name"], data[0]["date"]).lower()
        if name in _corrupted_expts:
            continue

        grp = h5_file.create_group(name)
        behavior_grp = grp.create_group("behavior")
        passive_grp = grp.create_group("passive")

        # get num trials
        _, n_trials_behavior, _ = data[0]['dff'].shape
        _, n_trials_passive, _ = data[1]['dff'].shape

        # both
        bad_trials = get_bad_trials(data)
        data[0]['dff'] = np.delete(data[0]['dff'], bad_trials[0], axis=1)
        data[1]['dff'] = np.delete(data[1]['dff'], bad_trials[1], axis=1)

        output = get_good_cells(data, nb_std=nb_std, norm_order=2)
        good_cells = [output[0][0], output[1][0]]

        behavior_grp.create_dataset("good_cells", data=good_cells[0], dtype=int)
        passive_grp.create_dataset("good_cells", data=good_cells[1], dtype=int)

        # behavior
        behavior_grp.create_dataset("dff", data=data[0]['dff'], dtype=float)
        behavior_grp.create_dataset("xy", data=data[0]['xy'], dtype=float)
        behavior_grp.create_dataset(
            "firstresponse", data=np.delete(data[0]['firstresponse'], bad_trials[0], axis=1), dtype=int)
        behavior_grp.create_dataset(
            "targetlick", data=np.delete(data[0]['targetlick'], bad_trials[0], axis=1), dtype=int)
        behavior_grp.create_dataset(
            "nontargetlick", data=np.delete(data[0]['nontargetlick'], bad_trials[0], axis=1), dtype=int)

        behavior_metadata_grp = behavior_grp.create_group("metadata")
        behavior_trials_grp = behavior_grp.create_group("trial_info")

        for k, v in data[0].items():
            if isinstance(v, (int, np.uint8, np.uint16)):
                behavior_metadata_grp.create_dataset(k, data=v)
            elif len(v) == n_trials_behavior:
                trial_data = np.delete(v, bad_trials[0])
                behavior_trials_grp.create_dataset(k, data=trial_data, dtype=int)
                if k == 'stimfrequency':
                    freqs = sorted(np.unique(trial_data))  # [7000, 9899, 14000, 19799]
                    target7k = np.zeros(len(trial_data))
                    target10k = np.zeros(len(trial_data))
                    nontarget14k = np.zeros(len(trial_data))
                    nontarget20k = np.zeros(len(trial_data))
                    target7k[np.where(trial_data == freqs[0])[0]] = 1
                    target10k[np.where(trial_data == freqs[1])[0]] = 1
                    nontarget14k[np.where(trial_data == freqs[2])[0]] = 1
                    nontarget20k[np.where(trial_data == freqs[3])[0]] = 1
                    behavior_trials_grp.create_dataset('target7k', data=target7k, dtype=int)
                    behavior_trials_grp.create_dataset('target10k', data=target10k, dtype=int)
                    behavior_trials_grp.create_dataset('nontarget14k', data=nontarget14k, dtype=int)
                    behavior_trials_grp.create_dataset('nontarget20k', data=nontarget20k, dtype=int)
            else:
                continue

        # passive
        passive_grp.create_dataset("dff", data=data[1]['dff'], dtype=float)
        passive_grp.create_dataset("xy", data=data[1]['xy'], dtype=float)

        passive_metadata_grp = passive_grp.create_group("metadata")
        passive_trials_grp = passive_grp.create_group("trial_info")

        for k, v in data[1].items():
            if isinstance(v, (int, np.uint8, np.uint16)):
                passive_metadata_grp.create_dataset(k, data=v)
            elif len(v) == n_trials_passive:
                passive_trials_grp.create_dataset(k, data=np.delete(v, bad_trials[1]), dtype=int)
            else:
                continue

    h5_file.close()


def get_bad_trials(data: List[dict]) -> List[int]:
    if not isinstance(data, list):
        data = [data]

    bad_trials = []
    for d in data:
        dff = d['dff']
        cells_norm = np.linalg.norm(dff, axis=0, ord=2)
        nan_norm = np.isnan(cells_norm)
        bad_trials.append(np.where(np.all(nan_norm, axis=1))[0])

    return bad_trials


def get_good_cells(data: List[dict], nb_std: int = 1, norm_order: int = 2) -> List[tuple]:
    if not isinstance(data, list):
        data = [data]

    output = []
    for d in data:
        cells_norm = np.linalg.norm(d['dff'], axis=0, ord=norm_order).mean(0)
        nonnan = ~np.isnan(cells_norm)
        nonnan_bright_cells = np.logical_and(d['bright_cells'], nonnan)
        nonnan_bright_indxs = np.where(nonnan_bright_cells == 1)[0]
        x = cells_norm[nonnan_bright_indxs]
        outlier_indxs = np.where(x - x.mean() > nb_std * x.std())[0]
        good_cells = np.delete(nonnan_bright_indxs, outlier_indxs)
        output.append((good_cells, outlier_indxs, nonnan_bright_indxs))

    return output


def plot_outlier_removal(
        data: List[dict],
        nb_std: int,
        norm_order: int = 2,
        save_dir: str = "outlier_removal") -> Tuple[int, int]:

    good_cells, outlier_indxs, nonnan_bright_indxs = get_good_cells(data, nb_std=nb_std, norm_order=norm_order)[0]
    cells_norm = np.linalg.norm(data[0]['dff'], axis=0, ord=2).mean(0)

    name = "{:s}_{:s}".format(data[0]["name"], data[0]["date"]).lower()
    msg = "--- Removing outliers from experiment '{:s}' ---\n\
    Good cells don't contain nan in any trial, but also:\n\
    \n 1) bright cells:  num bright = {:d}, tot = {:d}, => {:.1f}{:s}\
    \n 2) have norm that is within {:d} std of mean norm:\n\
    Outliers count: {:d}  == > {:.1f}{:s} of cells removed for this reason."
    msg = msg.format(name,
                     sum(data[0]['bright_cells']), len(data[0]['bright_cells']),
                     sum(data[0]['bright_cells']) / len(data[0]['bright_cells']) * 100, '%',
                     nb_std, len(outlier_indxs), len(outlier_indxs) / len(nonnan_bright_indxs) * 100, '%', )

    fig, ax_arr = plt.subplots(nrows=1, ncols=3, figsize=(18, 3), sharey='row', dpi=100)
    sup = fig.suptitle(msg, y=1.4, fontsize=15,)

    ax_arr[0].plot(cells_norm)
    ax_arr[0].set_ylabel("Norm")
    ax_arr[0].set_xlabel("All Cells. Count = {:d}".format(len(cells_norm)))

    ax_arr[1].plot(cells_norm[nonnan_bright_indxs])
    ax_arr[1].set_xlabel("Good Cells w/ Outliers. Count = {:d}".format(len(nonnan_bright_indxs)))

    ax_arr[2].plot(cells_norm[good_cells])
    ax_arr[2].set_xlabel("Good Cells, w/o outliers. Count = {:d}".format(len(good_cells)))

    save_folder = pjoin(save_dir, "nb_std={:d}".format(nb_std))
    os.makedirs(save_folder, exist_ok=True)
    save_file = pjoin(save_folder, "{:s}.pdf".format(name))
    fig.savefig(save_file, dpi=fig.dpi, bbox_inches='tight', bbox_extra_artists=[sup])
    plt.close()

    return len(outlier_indxs), len(nonnan_bright_indxs)


def _setup_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--nb_std",
        help="outlier removal threshold",
        type=int,
        default=1,
    )
    parser.add_argument(
        "--verbose",
        help="verbosity",
        action="store_true",
    )
    parser.add_argument(
        "--base_dir",
        help="base dir where project is saved",
        type=str,
        default='Documents/A1',
    )

    return parser.parse_args()


def main():
    args = _setup_args()

    base_dir = pjoin(os.environ['HOME'], args.base_dir)
    organize_data(base_dir=base_dir, nb_std=args.nb_std)

    processed_dir = pjoin(base_dir, 'python_processed')
    save_dir = pjoin(processed_dir, "processed_nb_std={:d}".format(args.nb_std))
    h_load_file = pjoin(processed_dir, "organized_nb_std={:d}.h5".format(args.nb_std))
    process_data(load_file=h_load_file, save_dir=save_dir, normalize=False)

    print("[PROGRESS] done.\n")


if __name__ == "__main__":
    main()
