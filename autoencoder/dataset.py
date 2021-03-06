import h5py
import numpy as np
import pandas as pd
from typing import Dict
from collections import Counter

from torch.utils.data import Dataset, DataLoader
from torch.utils.data.sampler import WeightedRandomSampler, RandomSampler
from utils.generic_utils import reset_df


class ClassifierDataset(Dataset):
    def __init__(
            self,
            x: np.ndarray,
            y: np.ndarray,
            z: np.ndarray,
            transform=None,
    ):
        assert len(x) == len(y) == len(z), "input/output num samples must be equal"
        self.x = x
        self.y = y
        self.z = z
        self.transform = transform

    def __len__(self):
        return len(self.y)

    def __getitem__(self, idx):
        x = self.x[idx]
        y = self.y[idx]
        z = self.z[idx]

        if self.transform is not None:
            x = self.transform(x)
            z = self.transform(z)
        return x, y, z


def create_clf_dataset(output_train: dict, output_valid: dict, batch_size: int):
    x_trn = output_train['x']
    y_trn = output_train['y']
    z_trn = output_train['z']
    x_vld = output_valid['x']
    y_vld = output_valid['y']
    z_vld = output_valid['z']

    ds_train = ClassifierDataset(x_trn, y_trn, z_trn, None)
    ds_valid = ClassifierDataset(x_vld, y_vld, z_vld, None)

    dl_train = DataLoader(
        dataset=ds_train,
        batch_size=batch_size,
        shuffle=True,
        drop_last=True,)
    dl_valid = DataLoader(
        dataset=ds_valid,
        batch_size=batch_size,
        shuffle=False,
        drop_last=False,)

    return dl_train, dl_valid


class A1Dataset(Dataset):
    def __init__(
            self,
            dff: Dict[str, np.ndarray],
            licks: Dict[str, np.ndarray],
            ranges: Dict[str, tuple],
            df: pd.DataFrame,
            l2i: Dict[str, int] = None,
            f2i: Dict[int, int] = None,
            n2i: Dict[str, int] = None,
            transform=None,
    ):
        self.dff = dff
        self.licks = licks
        self.ranges = ranges
        self.df = df
        self.l2i = l2i
        self.f2i = f2i
        self.n2i = n2i
        self.transform = transform
        self.sample_weights = self._compute_sample_weights()

    def __len__(self):
        return sum([v.shape[1] for v in self.licks.values()])

    def __getitem__(self, idx):
        generator = self._generate_idxs(idx)
        names, labels, freqs, dffs, licks = [], [], [], [], []
        for name, i in generator:
            label = self.df.loc[self.df.name == name, 'label'].iloc[i]
            freq = self.df.loc[self.df.name == name, 'freq'].iloc[i]
            dff = self.dff[name][:, i, :]
            lick = self.licks[name][:, i]

            names.append(self.n2i[name])
            labels.append(self.l2i[label])
            freqs.append(self.f2i[freq])
            dffs.append(np.transpose(dff)[np.newaxis, ...])
            licks.append(lick[np.newaxis, :, np.newaxis])

        names, labels, freqs = tuple(map(lambda x: np.array(x), [names, labels, freqs]))
        licks = np.concatenate(licks)

        if self.transform is not None:
            dffs = self.transform(dffs)

        data = {
            'name': names,
            'label': labels,
            'freq': freqs,
            'dff': dffs,
            'lick': licks,
        }
        return data

    def _generate_idxs(self, idx):
        if isinstance(idx, int):
            idxs = [idx]
        elif isinstance(idx, (list, range)):
            idxs = idx
        elif isinstance(idx, slice):
            start, stop, stride = idx.indices(len(self))
            idxs = range(start, stop, stride)
        else:
            raise RuntimeError("invalid indexing encountered")
        return ((k, idx - a) for idx in idxs for k, (a, b) in self.ranges.items() if a <= idx < b)

    def _compute_sample_weights(self):
        w = np.ones(len(self))
        label_freqs = Counter(self.df.label)
        for elem, f in label_freqs.most_common():
            indices = np.where(self.df.label == elem)[0]
            w[indices] = 1 / f
        return w


def create_a1_dataset(config, train_config):
    ds_train, ds_valid = _create_ds(config, train_config)

    if train_config.balanced_sampling:
        sampler = WeightedRandomSampler(
            weights=ds_train.sample_weights,
            num_samples=train_config.batch_size,
            replacement=train_config.replacement,)
    else:
        sampler = RandomSampler(
            data_source=ds_train,
            num_samples=train_config.batch_size,
            replacement=True,)

    return sampler, ds_train, ds_valid


def _create_ds(config, train_config):

    f = h5py.File(config.h_file, 'r')
    dff_all = {}
    licks_all = {}
    df = pd.DataFrame()

    for name in f:
        behavior = f[name]['behavior']
        passive = f[name]['passive']

        good_cells_b = np.array(behavior["good_cells"], dtype=int)
        good_cells_p = np.array(passive["good_cells"], dtype=int)

        good_cells = set(good_cells_b).intersection(set(good_cells_p))
        good_cells = sorted(list(good_cells))

        xy = np.array(behavior["xy"], dtype=float)[good_cells]  # TODO: figure out xy
        dff_b = np.array(behavior["dff"], dtype=float)[..., good_cells]
        dff_p = np.array(passive["dff"], dtype=float)[..., good_cells]
        ntrials_b = dff_b.shape[1]
        ntrials_p = dff_p.shape[1]
        dff = np.concatenate([dff_b, dff_p], axis=1)

        behavior_trial_info_grp = behavior["trial_info"]
        passive_trial_info_grp = passive["trial_info"]

        trial_info_b = {}
        for k, v in behavior_trial_info_grp.items():
            trial_info_b[k] = np.array(v, dtype=int)

        trial_info_p = {}
        for k, v in passive_trial_info_grp.items():
            trial_info_p[k] = np.array(v, dtype=int)

        # licks
        targetlick = np.array(behavior['targetlick'])
        nontargetlick = np.array(behavior['nontargetlick'])

        nt = len(dff)
        licks = np.zeros((nt, ntrials_b))
        licks[:, trial_info_b['target'] == 1] = targetlick[:, trial_info_b['target'] == 1]
        licks[:, trial_info_b['nontarget'] == 1] = nontargetlick[:, trial_info_b['nontarget'] == 1]
        licks = np.concatenate([licks, np.zeros((nt, ntrials_p))], axis=1)

        # labels (behavior only)
        trial_labels = {idx: '_null_' for idx in range(ntrials_b)}
        for k, v in trial_info_b.items():
            if 'target' not in k:
                for i in np.where(v == 1)[0]:
                    trial_labels[i] = k
        # add passive labels in there
        trial_labels.update({idx: 'passive' for idx in range(ntrials_b, ntrials_b + ntrials_p)})

        # stim freqs (passive)
        stim_freqs = np.concatenate([trial_info_b['stimfrequency'], trial_info_p['stimfrequency']])

        if '_null_' in trial_labels.values():
            print('warning', name)
        assert dff.shape[1] == licks.shape[1] == len(trial_labels) == len(stim_freqs)

        trial_bool = [True if trial in config.include_trials else False for trial in trial_labels.values()]
        freq_bool = np.in1d(stim_freqs, config.include_freqs)

        include_indxs = np.where(np.logical_and(trial_bool, freq_bool))[0]
        trials = [lbl for idx, lbl in trial_labels.items() if idx in include_indxs]
        freqs = stim_freqs[include_indxs]
        licks = licks[:, include_indxs]
        dff = dff[:, include_indxs, :]
        nt, ntrials, nc = dff.shape

        dff_all[name] = dff
        licks_all[name] = licks

        data_dict = {
            'name': [name] * ntrials,
            'nb_cells': [nc] * ntrials,
            'label': trials,
            'freq': freqs,
        }
        df = pd.concat([df, pd.DataFrame.from_dict(data_dict)])
    df = reset_df(df)
    f.close()

    outputs_train, outputs_valid = _train_valid_split(
        dff_all, licks_all, train_config.xv_folds, train_config.random_state)
    dff_train, licks_train, ranges_train, train_indxs = outputs_train
    dff_valid, licks_valid, ranges_valid, valid_indxs = outputs_valid

    ds_train = A1Dataset(
        dff=dff_train,
        licks=licks_train,
        ranges=ranges_train,
        df=df.iloc[np.concatenate([*train_indxs.values()])],
        l2i=config.l2i,
        f2i=config.f2i,
        n2i=config.n2i,
        transform=None,)
    ds_valid = A1Dataset(
        dff=dff_valid,
        licks=licks_valid,
        ranges=ranges_valid,
        df=df.iloc[np.concatenate([*valid_indxs.values()])],
        l2i=config.l2i,
        f2i=config.f2i,
        n2i=config.n2i,
        transform=None,)

    return ds_train, ds_valid


def _train_valid_split(dff_all, licks_all, xv_folds, random_state):
    rng = np.random.RandomState(random_state)

    dff_valid = {}
    dff_train = {}

    licks_valid = {}
    licks_train = {}

    valid_indxs = {}
    train_indxs = {}

    last_idx = 0
    for name, dff in dff_all.items():
        num_samples = dff.shape[1]

        valid_ = rng.choice(np.arange(num_samples), size=num_samples // xv_folds, replace=False)
        valid_ = sorted(valid_)
        train_ = np.delete(np.arange(num_samples), valid_)

        dff_valid[name] = dff[:, valid_, :]
        dff_train[name] = dff[:, train_, :]

        licks_valid[name] = licks_all[name][:, valid_]
        licks_train[name] = licks_all[name][:, train_]

        valid_indxs[name] = [i + last_idx for i in valid_]
        train_indxs[name] = [i + last_idx for i in train_]

        last_idx += num_samples

    ranges_train = {}
    last_idx = 0
    for k, v in train_indxs.items():
        ranges_train[k] = (last_idx, last_idx + len(v))
        last_idx += len(v)

    ranges_valid = {}
    last_idx = 0
    for k, v in valid_indxs.items():
        ranges_valid[k] = (last_idx, last_idx + len(v))
        last_idx += len(v)

    outputs_train = (dff_train, licks_train, ranges_train, train_indxs)
    outputs_valid = (dff_valid, licks_valid, ranges_valid, valid_indxs)

    return outputs_train, outputs_valid
