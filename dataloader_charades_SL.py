" Dataloader of charades-STA dataset for Supervised Learning based methods"

import torch
import torch.utils.data
import os
import pickle
import numpy as np
import math
from utils import *
import random

class Charades_Train_dataset(torch.utils.data.Dataset):
    def __init__(self):
        self.unit_size = 16
        self.feats_dimen = 4096
        self.context_num = 1
        self.context_size = 128
        self.visual_feature_dim = 4096 * 3
        self.sent_vec_dim = 4800
        self.clip_softmax_dim = 400
        self.softmax_unit_size = 32
        self.spacy_vec_dim = 300
        self.train_softmax_dir = './Dataset/Charades/train_softmax/'
        self.sliding_clip_path = "./Dataset/Charades/all_fc6_unit16_overlap0.5/"
        #self.clip_sentence_pairs_iou = pickle.load(open("./Dataset/Charades/ref_info/charades_sta_train_semantic_sentence_VP_sub_obj.pkl"))
        self.clip_sentence_pairs_iou = read_pkl_file("./Dataset/Charades/ref_info/charades_sta_train_semantic_sentence_VP_sub_obj.pkl")
        # self.clip+sentence_pairs_iou is a dictionary
        # name of the videos are the keys
        # each element with key is another dictionary
        # each movie clip contains many things
        self.num_videos = len(self.clip_sentence_pairs_iou)  # 5182
        
        # get the number of self.clip_sentence_pairs_iou
        self.clip_sentence_pairs_iou_all = []
        # ii here is the movie name
        for ii in self.clip_sentence_pairs_iou:
            # iii here is each clip
            for iii in self.clip_sentence_pairs_iou[ii]:
                # in each clip there are multiple different information
                for iiii in range(len(self.clip_sentence_pairs_iou[ii][iii])):
                    self.clip_sentence_pairs_iou_all.append(self.clip_sentence_pairs_iou[ii][iii][iiii])
                    # basically its appending all clip sentence pair in a list 

        self.num_samples_iou = len(self.clip_sentence_pairs_iou_all)
        print(self.num_samples_iou, "iou clip-sentence pairs are readed")  # 49442

        # print self.clip_sentence_pairs_iou
        self.movie_length_dict = {}
        with open("./Dataset/Charades/ref_info/charades_movie_length_info.txt")  as f:
            for l in f:
                self.movie_length_dict[l.rstrip().split(" ")[0]] = float(l.rstrip().split(" ")[1])

    def read_unit_level_feats(self, clip_name):
        # read unit level feats by just passing the start and end number
        # clip_name is from clip_sentence_pair: proposal_or_sliding_window
        
        # lets say for 004QE_449_577
        movie_name = clip_name.split("_")[0] # name of the movie: 004QE
        start = int(clip_name.split("_")[1])  # starting frame: 449
        end = int(clip_name.split("_")[2]) # ending frame: 577
        num_units = (end - start) / self.unit_size  #why dividing by 16?  577-449=128, 128/16=8
        # print(start, end, num_units)

        curr_start = start # 449

        start_end_list = []  
        while (curr_start + self.unit_size <= end):
            start_end_list.append((curr_start, curr_start + self.unit_size)) #(449,449+16),(465,465+16)
            curr_start += self.unit_size

        original_feats = np.zeros([num_units, self.feats_dimen], dtype=np.float32)
        for k, (curr_s, curr_e) in enumerate(start_end_list):
            one_feat = np.load(self.sliding_clip_path + movie_name + "_" + str(curr_s) + ".0_" + str(curr_e) + ".0.npy")
            # so basically the numpy files conain the frame number with .0 added 
            # why the starting time always match, because it is always sampled in the same way? why didn't i found anything sampled with sampled window 64?
            original_feats[k] = one_feat

        return np.mean(original_feats, axis=0)

    def read_unit_level_softmax(self, clip_name):
        # read unit level softmax by just passing the start and end number
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])
        num_units = (end - start) / self.unit_size - (self.softmax_unit_size / self.unit_size) + 1
        _is_clip_shorter_than_unit_size = False
        if num_units <= 0:
            num_units = 1
            _is_clip_shorter_than_unit_size = True

        softmax_feats = np.zeros([num_units, self.clip_softmax_dim], dtype=np.float32)
        if _is_clip_shorter_than_unit_size:
            _start_here = start
            _end_here = end
            _npy_file_path_this = self.train_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(
                curr_e) + ".npy"
            if not os.path.exists(_npy_file_path_this):
                _npy_file_path_this = self.train_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(
                    curr_e) + ".npy"
            one_feat = np.load(_npy_file_path_this)
            softmax_feats[0] = one_feat

        else:
            curr_start = start
            start_end_list = []
            while (curr_start + self.softmax_unit_size <= end):
                start_end_list.append((curr_start, curr_start + self.softmax_unit_size))
                curr_start += self.unit_size
            for k, (curr_s, curr_e) in enumerate(start_end_list):
                one_feat = np.load(
                    self.train_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(curr_e) + ".npy")
                softmax_feats[k] = one_feat

        return np.mean(softmax_feats, axis=0)

    def feat_exists(self, clip_name):
        # judge the feats is existed or not
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])

        return os.path.exists(
            self.sliding_clip_path + movie_name + "_" + str(end - 16) + ".0_" + str(end) + ".0.npy") and \
               os.path.exists(
                   self.sliding_clip_path + movie_name + "_" + str(start) + ".0_" + str(start + 16) + ".0.npy")

    def get_context_window(self, clip_name, win_length):
        # compute left (pre) and right (post) context features based on read_unit_level_feats().
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])
        clip_length = self.context_size
        left_context_feats = np.zeros([win_length, self.feats_dimen], dtype=np.float32)
        right_context_feats = np.zeros([win_length, self.feats_dimen], dtype=np.float32)
        last_left_feat = self.read_unit_level_feats(clip_name)
        last_right_feat = self.read_unit_level_feats(clip_name)
        for k in range(win_length):
            left_context_start = start - clip_length * (k + 1)
            left_context_end = start - clip_length * k
            right_context_start = end + clip_length * k
            right_context_end = end + clip_length * (k + 1)
            left_context_name = movie_name + "_" + str(left_context_start) + "_" + str(left_context_end)
            right_context_name = movie_name + "_" + str(right_context_start) + "_" + str(right_context_end)
            if self.feat_exists(left_context_name):
                left_context_feat = self.read_unit_level_feats(left_context_name)
                last_left_feat = left_context_feat
            else:
                left_context_feat = last_left_feat
            if self.feat_exists(right_context_name):
                right_context_feat = self.read_unit_level_feats(right_context_name)
                last_right_feat = right_context_feat
            else:
                right_context_feat = last_right_feat
            left_context_feats[k] = left_context_feat
            right_context_feats[k] = right_context_feat
        return np.mean(left_context_feats, axis=0), np.mean(right_context_feats, axis=0)

    def __getitem__(self, index):

        offset = np.zeros(2, dtype=np.float32)
        VP_spacy = np.zeros(self.spacy_vec_dim*2, dtype=np.float32)

        # get this clip's: sentence  vector, swin, p_offest, l_offset, sentence, Vps
        dict_3rd = self.clip_sentence_pairs_iou_all[index]
        # read visual feats
        featmap = self.read_unit_level_feats(dict_3rd['proposal_or_sliding_window'])
        left_context_feat, right_context_feat = self.get_context_window(dict_3rd['proposal_or_sliding_window'], self.context_num)
        image = np.hstack((left_context_feat, featmap, right_context_feat))

        # read softmax batch
        softmax_center_clip = self.read_unit_level_softmax(dict_3rd['proposal_or_sliding_window'])

        # sentence batch
        sentence = dict_3rd['sent_skip_thought_vec'][0][0, :self.sent_vec_dim]

        if len(dict_3rd['dobj_or_VP']) != 0:
            VP_spacy_one_by_one_this_ = dict_3rd['VP_spacy_vec_one_by_one_word'][random.choice(xrange(len(dict_3rd['dobj_or_VP'])))]
            if len(VP_spacy_one_by_one_this_) == 1:
                VP_spacy[:self.spacy_vec_dim] = VP_spacy_one_by_one_this_[0]
            else:
                VP_spacy = np.concatenate((VP_spacy_one_by_one_this_[0], VP_spacy_one_by_one_this_[1]))

        # offest
        p_offset = dict_3rd['offset_start']
        l_offset = dict_3rd['offset_end']
        offset[0] = p_offset
        offset[1] = l_offset

        return image, sentence, offset, softmax_center_clip, VP_spacy

    def __len__(self):
        return self.num_samples_iou



class Charades_Test_dataset(torch.utils.data.Dataset):
    def __init__(self):

        # il_path: image_label_file path
        self.context_num = 1
        self.context_size = 128
        self.visual_feature_dim = 4096 * 3
        self.feats_dimen = 4096
        self.unit_size = 16
        self.context_size = 128
        self.semantic_size = 4800
        self.sliding_clip_path = "./Dataset/Charades/all_fc6_unit16_overlap0.5/"
        self.index_in_epoch = 0
        self.spacy_vec_dim = 300
        self.sent_vec_dim = 4800
        self.clip_softmax_dim = 400
        self.softmax_unit_size = 32
        self.test_softmax_dir =  './Dataset/Charades/test_softmax/'
        self.epochs_completed = 0
        self.test_swin_txt_path = "./Dataset/Charades/ref_info/charades_sta_test_swin_props_num_36364.txt"

        # self.clip_sentence_pairs = pickle.load(open("./Dataset/Charades/ref_info/charades_sta_test_semantic_sentence_VP_sub_obj.pkl"))
        self.clip_sentence_pairs = read_pkl_file("./Dataset/Charades/ref_info/charades_sta_test_semantic_sentence_VP_sub_obj.pkl")
        print (str(len(self.clip_sentence_pairs)) + " test videos are readed")  # 1334
        
        self.clip_sentence_test = read_pkl_file('./Dataset/Charades/ref_info/aligned_testset.pkl')
        # need a list of clip sentence pair
        self.clip_sentence_test_list = []
        for movie in self.clip_sentence_test:   
            for clip in self.clip_sentence_test[movie]:   # self.clip_sentence_test[movie] is a dict
                for elem in self.clip_sentence_test[movie][clip]:  # self.clip_sentence_test[movie][clip] is a list
                    if bool(elem):
                        elem['clip_name'] = clip
                        self.clip_sentence_test_list.append(elem)
        self.num_of_test_clips = len(self.clip_sentence_test_list)
        
        
        
        # need a list of clip sentence pair
        self.clip_sentence_pairs_list = []
        for i in self.clip_sentence_pairs:   
            for ii in self.clip_sentence_pairs[i]:   # self.clip_sentence_pair[movie_name] is a dict
                for iii in self.clip_sentence_pairs[i][ii]:  # self.clip_sentence_pair[movie_name][clip_name] is a list
                    # iii is an element of list
                    iii['clip_name'] = ii
                    self.clip_sentence_pairs_list.append(iii)
        
        
        movie_names_set = set()
        for ii in self.clip_sentence_pairs:
            for iii in self.clip_sentence_pairs[ii]:
                clip_name = iii
                movie_name = ii
                if not movie_name in movie_names_set:
                    movie_names_set.add(movie_name)
        self.movie_names = list(movie_names_set)

        # does it has same index number as self.clip_sentence_pair_list
        self.sliding_clip_names = []
        with open(self.test_swin_txt_path) as f:
            for l in f:
                self.sliding_clip_names.append(l.rstrip().replace(" ", "_"))
        print("sliding clips number for test: " + str(len(self.sliding_clip_names)))  # 36364
        # contains movie-name_other info for per clip

        self.movie_length_dict = {}
        with open("./Dataset/Charades/ref_info/charades_movie_length_info.txt")  as f:
            for l in f:
                self.movie_length_dict[l.rstrip().split(" ")[0]] = float(l.rstrip().split(" ")[1])
        
        # movie names
        # sliding clip names ? full details but why? 
        # movie lengths


    def read_unit_level_feats(self, clip_name):
        # what is clip length here?
        # read unit level feats by just passing the start and end number
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])
        num_units = int((end - start) / self.unit_size)
        curr_start = start

        start_end_list = []
        while (curr_start + self.unit_size <= end):
            start_end_list.append((curr_start, curr_start + self.unit_size))
            curr_start += self.unit_size

        original_feats = np.zeros([num_units, self.feats_dimen], dtype=np.float32)
        for k, (curr_s, curr_e) in enumerate(start_end_list):
            one_feat = np.load(self.sliding_clip_path + movie_name + "_" + str(curr_s) + ".0_" + str(curr_e) + ".0.npy")
            original_feats[k] = one_feat

        return np.mean(original_feats, axis=0)

    def read_unit_level_softmax(self, clip_name):
        # read unit level softmax by just passing the start and end number
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])
        num_units = int((end - start) / self.unit_size - (self.softmax_unit_size / self.unit_size) + 1)
        _is_clip_shorter_than_unit_size = False
        if num_units <= 0:
            num_units = 1
            _is_clip_shorter_than_unit_size = True

        softmax_feats = np.zeros([num_units, self.clip_softmax_dim], dtype=np.float32)
        if _is_clip_shorter_than_unit_size:
            _start_here = start
            _end_here = end
            _npy_file_path_this = self.test_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(
                curr_e) + ".npy"
            if not os.path.exists(_npy_file_path_this):
                _npy_file_path_this = self.test_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(
                    curr_e) + ".npy"
            one_feat = np.load(_npy_file_path_this)
            softmax_feats[0] = one_feat

        else:
            curr_start = start
            start_end_list = []
            while (curr_start + self.softmax_unit_size <= end):
                start_end_list.append((curr_start, curr_start + self.softmax_unit_size))
                curr_start += self.unit_size
            for k, (curr_s, curr_e) in enumerate(start_end_list):
                one_feat = np.load(
                    self.test_softmax_dir + movie_name + ".mp4_" + str(curr_s) + "_" + str(curr_e) + ".npy")
                softmax_feats[k] = one_feat

        return np.mean(softmax_feats, axis=0)


    def feat_exists(self, clip_name):
        # judge the feats is existed or not
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])

        return os.path.exists(
            self.sliding_clip_path + movie_name + "_" + str(end - 16) + ".0_" + str(end) + ".0.npy") and \
               os.path.exists(
                   self.sliding_clip_path + movie_name + "_" + str(start) + ".0_" + str(start + 16) + ".0.npy")

    def get_context_window(self, clip_name, win_length):
        # compute left (pre) and right (post) context features based on read_unit_level_feats().
        movie_name = clip_name.split("_")[0]
        start = int(clip_name.split("_")[1])
        end = int(clip_name.split("_")[2])
        clip_length = self.context_size
        left_context_feats = np.zeros([win_length, self.feats_dimen], dtype=np.float32)
        right_context_feats = np.zeros([win_length, self.feats_dimen], dtype=np.float32)
        last_left_feat = self.read_unit_level_feats(clip_name)
        last_right_feat = self.read_unit_level_feats(clip_name)
        for k in range(win_length):
            left_context_start = start - clip_length * (k + 1)
            left_context_end = start - clip_length * k
            right_context_start = end + clip_length * k
            right_context_end = end + clip_length * (k + 1)
            left_context_name = movie_name + "_" + str(left_context_start) + "_" + str(left_context_end)
            right_context_name = movie_name + "_" + str(right_context_start) + "_" + str(right_context_end)
            if self.feat_exists(left_context_name):
                left_context_feat = self.read_unit_level_feats(left_context_name)
                last_left_feat = left_context_feat
            else:
                left_context_feat = last_left_feat
            if self.feat_exists(right_context_name):
                right_context_feat = self.read_unit_level_feats(right_context_name)
                last_right_feat = right_context_feat
            else:
                right_context_feat = last_right_feat
            left_context_feats[k] = left_context_feat
            right_context_feats[k] = right_context_feat
        return np.mean(left_context_feats, axis=0), np.mean(right_context_feats, axis=0)


    def load_movie_slidingclip(self, movie_name, sample_num):
        # load unit level feats and sentence vector
        movie_clip_sentences = []
        movie_clip_featmap = []

        for dict_2nd in self.clip_sentence_pairs[movie_name]:  # dict_2nd contains all clip?
            for dict_3rd in self.clip_sentence_pairs[movie_name][dict_2nd]: 

                VP_spacy_vec_ = np.zeros(self.spacy_vec_dim * 2)
                subj_spacy_vec_ = np.zeros(self.spacy_vec_dim)
                obj_spacy_vec_ = np.zeros(self.spacy_vec_dim)

                if len(dict_3rd['dobj_or_VP']) != 0:
                    VP_spacy_one_by_one_this_ = dict_3rd['VP_spacy_vec_one_by_one_word'][
                        random.choice(xrange(len(dict_3rd['dobj_or_VP'])))]
                    if len(VP_spacy_one_by_one_this_) == 1:
                        VP_spacy_vec_[:self.spacy_vec_dim] = VP_spacy_one_by_one_this_[0]
                    else:
                        VP_spacy_vec_ = np.concatenate((VP_spacy_one_by_one_this_[0], VP_spacy_one_by_one_this_[1]))
                if len(dict_3rd['subj']) != 0:
                    subj_spacy_vec_ = dict_3rd['subj_spacy_vec'][random.choice(xrange(len(dict_3rd['subj'])))]
                if len(dict_3rd['obj']) != 0:
                    obj_spacy_vec_ = dict_3rd['obj_spacy_vec'][random.choice(xrange(len(dict_3rd['obj'])))]

                sentence_vec_ = dict_3rd['sent_skip_thought_vec'][0][0, :self.sent_vec_dim]
                # as looping inside dict_2nd (all clip)?
                
                movie_clip_sentences.append((dict_2nd, sentence_vec_, VP_spacy_vec_, subj_spacy_vec_, obj_spacy_vec_))
                # what does it contain??

        for k in xrange(len(self.sliding_clip_names)):
            if movie_name in self.sliding_clip_names[k]:
                left_context_feat, right_context_feat = self.get_context_window(self.sliding_clip_names[k],
                                                                                self.context_num)
                feature_data = self.read_unit_level_feats(self.sliding_clip_names[k])

                # read softmax batch
                softmax_center_clip = self.read_unit_level_softmax(self.sliding_clip_names[k])

                comb_feat = np.hstack((left_context_feat, feature_data, right_context_feat))
                movie_clip_featmap.append((self.sliding_clip_names[k], comb_feat, softmax_center_clip))
                # movie_clip_featmap.append((self.sliding_clip_na
        return movie_clip_featmap, movie_clip_sentences
        # movie_clip_featmap contains all the clip features
        # but movie_clip_sentence contains only the sentence?
        
    # loading movie feature on basis of clip names    
    def load_video_feature(self,clip_name):
        
        feature_data = self.read_unit_level_feats(clip_name)
        left_context_feat, right_context_feat = self.get_context_window(clip_name, self.context_num)
        comb_feat = np.hstack((left_context_feat, feature_data, right_context_feat))
        
        return comb_feat    

    # loading sentence feature on basis of clip names
    def load_sentence_feature(self,clip_name):
        
        for elem in self.clip_sentence_test_list:
            sentence_vec_ = elem['sent_skip_thought_vec'][0][0, :self.sent_vec_dim]
        return sentence_vec_
            
        
                 
    
    def __getitem__(self, index):

        # get this clip's: sentence  vector
        dict_3rd = self.clip_sentence_pairs_iou_list[index]
        # read visual feats
        featmap = self.read_unit_level_feats(dict_3rd['clip_name'])
        left_context_feat, right_context_feat = self.get_context_window(dict_3rd['clip_name'], self.context_num)
        image = np.hstack((left_context_feat, featmap, right_context_feat))

        # sentence batch
        sentence = dict_3rd['sent_skip_thought_vec'][0][0, :self.sent_vec_dim]

        return image, sentence

    def __len__(self):
        return self.num_of_test_clips
    

if __name__ == '__main__':
    #train_dataset = Charades_Train_dataset()
    test_dataset = Charades_Test_dataset()
    pairs = test_dataset.clip_sentence_pairs
    pair_list = test_dataset.clip_sentence_pairs_list
    pair_len = len(test_dataset)
    
    '''
    num_of_pair = 0
    for key1 in pairs:
        for key2 in pairs[key1]:
            for key3 in pairs[key1][key2]:
                num_of_pair+=1
            
    a=1
    '''
