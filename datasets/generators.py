import os
import h5py
import torch
import random
import numpy as np
import pickle as pk

from torch.utils.data import Dataset
from skimage.transform import resize

        
class DatasetGenerator(torch.utils.data.Dataset):
    def __init__(self, feature_file, videos, min_len=4):
        self.feature_file = h5py.File(feature_file, "r")
        self.videos = videos
        self.min_len = min_len

    def __len__(self):
        return len(self.videos)
    
    def __getitem__(self, idx):
        try:
            video_id = self.videos[idx]
            features = self.feature_file[video_id][:]
            while features.shape[0] < self.min_len:
                features = np.concatenate([features, features], axis=0)
            if features.ndim == 2: 
                features = np.expand_dims(features, 1)
            return torch.from_numpy(features.astype(np.float32)), video_id
        except Exception as e:
            return torch.zeros((1, 9, 512)), ''

class VideoPairGenerator(Dataset):

    def __init__(self, args):
        super(VideoPairGenerator, self).__init__()
        print('\n> Create generator of video pairs')
        print('>> loading pairs ...')
        ground_truths = pk.load(open('data/trainset_similarities_{}.pk'.format(args.teacher), 'rb'))
        self.index = ground_truths['index']
        self.pairs = ground_truths['pairs']
        self.feature_file = h5py.File(args.trainset_hdf5, "r")
        self.augmentation = args.augmentation
        self.selected_pairs = []
        self.normalize = args.student_type == 'coarse-grained'
        
        self.video_set = list(np.arange(len(self.index)))
        np.random.shuffle(self.video_set)
        self.video_set = set(self.video_set[:int(len(self.index)*args.trainset_percentage/100)])

    def next_epoch(self):
        self.selected_pairs = self.select_pairs()

    def select_pairs(self):
        selected_pairs = []
        for q, t in self.pairs.items():
            pos = [v for v in list(t['positives'].keys()) if v in self.video_set]
            neg = [v for v in list(t['negatives'].keys()) if v in self.video_set]
            if q in self.video_set and pos and neg:
                p = random.choice(pos)
                n = random.choice(neg)
                sim_p = t['positives'][p]
                sim_n = t['negatives'][n]
                if self.normalize:
                    sim_p = sim_p / 2. + 0.5
                    sim_n = sim_n / 2. + 0.5
                selected_pairs.append([q, p, n, float(sim_p), float(sim_n)])
        return selected_pairs
                        
    def load_video(self, video, augmentation=False):
        video_tensor = self.feature_file[str(self.index[video])][:]
        if augmentation:
            video_tensor = self.augment(video_tensor)
        return torch.from_numpy(video_tensor.astype(np.float32))

    def augment(self, video):
        if video.shape[0] > 6:
            rnd = np.random.uniform()
            if rnd < 0.1:
                mask = np.random.rand(video.shape[0]) > 0.3
                if np.sum(mask):
                    video = video[mask]
            elif rnd < 0.2:
                video = video[::2]
            elif rnd < 0.3:
                if video.shape[0] < 150:
                    idx = np.insert(np.arange(len(video)), np.arange(len(video)), np.arange(len(video)))
                    video = video[idx]
        return video

    def __len__(self):
        return len(self.selected_pairs)

    def __getitem__(self, index):
        pairs = self.selected_pairs[index]
        anchor = self.load_video(pairs[0])
        positive = self.load_video(pairs[1], augmentation=self.augmentation)
        negative = self.load_video(pairs[2], augmentation=self.augmentation)
        simimarities = torch.tensor(pairs[3:])
        return anchor, positive, negative, simimarities.unsqueeze(0)
