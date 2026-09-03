from HParams import HParams
from Evaluater.Evaluater import Evaluater
import soundfile as sf
from scipy.io import wavfile
import numpy as np
import museval
import os
import librosa
from scipy.spatial.distance import euclidean
import pysptk
from fastdtw import fastdtw
import Evaluater.MetricVoice as vm
from Evaluater.MetricVoice import MetricVoice

class EvaluaterSVS(Evaluater):
    def __init__(self, h_params: HParams):
        super().__init__(h_params)
        self.pred_gt_name_dict = h_params.evaluate.pred_gt_dict
        self.voice_metric = MetricVoice(self.h_params)
    
    def read_pred_gt_list(self,data_name,read_module_name="librosa"):
        '''
        "key": Pred", gt:
        ["key",.."key"...]
        ["key":sdr]
        return {"pred": list, "gt" : list}
        '''
        file_path = f"{self.data_path}/{data_name}"

        pred_gt_dict = dict()
        
        for data_name in self.pred_gt_name_dict:
            pred_gt_dict[data_name] = dict()
            if read_module_name == "soundfile":
                pred_gt_dict[data_name]["gt"],sr = sf.read(f"{file_path}/{self.pred_gt_name_dict[data_name]['gt_audio_file_name']}")
                pred_gt_dict[data_name]["pred"],sr = sf.read(f"{file_path}/{self.pred_gt_name_dict[data_name]['pred_audio_file_name']}")
            elif read_module_name == "librosa":
                pred_gt_dict[data_name]["gt"],sr = librosa.load(f"{file_path}/{self.pred_gt_name_dict[data_name]['gt_audio_file_name']}",sr=None)
                pred_gt_dict[data_name]["pred"],sr = librosa.load(f"{file_path}/{self.pred_gt_name_dict[data_name]['pred_audio_file_name']}",sr=None)
            assert pred_gt_dict[data_name]["gt"].shape == pred_gt_dict[data_name]["pred"].shape, "pred shape and gt shape shoud be same"
        return pred_gt_dict

    def evaluator(self,test_set_dict) -> dict:
        '''
        references : np.ndarray, shape=(nsrc, nsampl, nchan)
            array containing true reference sources
        estimates : np.ndarray, shape=(nsrc, nsampl, nchan)
            array containing estimated sources
            
        return evaluation resutl
        '''
        final_evaluation_dict = dict()

        data_name_list = []
        references_list = [] #gt
        estimates_list = [] #pred
        for data_name in test_set_dict:
            final_evaluation_dict[data_name] = dict()
            data_name_list.append(data_name)
            references_list.append(test_set_dict[data_name]['gt'])
            estimates_list.append(test_set_dict[data_name]['pred'])
            if 'voice' in data_name:
                print("get_mcd")
                
                mcd, length =vm.get_mcd(    source=test_set_dict[data_name]['pred'],
                                    target=test_set_dict[data_name]['gt'],
                                    sample_rate=self.h_params.preprocess.sample_rate)
                final_evaluation_dict[data_name]["MCD"] = mcd
                sispnr = self.voice_metric.get_sispnr(pred_audio=test_set_dict[data_name]['pred'],target_audio=test_set_dict[data_name]['gt'])
                final_evaluation_dict[data_name].update(sispnr)
                sdr_torchmetrics:dict = self.voice_metric.get_sdr_torchmetrics(pred_audio=test_set_dict[data_name]['pred'],target_audio=test_set_dict[data_name]['gt'])
                final_evaluation_dict[data_name].update(sdr_torchmetrics)
                
        print("get SDR, ISR, SIR, SAR")
        SDR, ISR, SIR, SAR = museval.evaluate(references=references_list,estimates=estimates_list)
        evaluation_dict = {"SDR":SDR,"ISR":ISR,"SIR":SIR,"SAR":SAR}
        
        for i,data_name in enumerate(data_name_list):
            for metric in evaluation_dict:
                evaluation_metric = evaluation_dict[metric][i]
                evaluation_metric = evaluation_metric[np.isfinite(evaluation_metric)]
                final_evaluation_dict[data_name][metric] = np.median(evaluation_metric)
        return final_evaluation_dict
    
    
    def mcd_eval(self,ref_vocal, estimate_vocal):
        _logdb_const = 10.0 / np.log(10.0) * np.sqrt(2.0)

        mgc1 = self.readmgc(ref_vocal)
        mgc2 = self.readmgc(estimate_vocal)

        x = mgc1
        y = mgc2

        distance, path = fastdtw(x, y, dist=euclidean)

        distance/= (len(x) + len(y))
        pathx = list(map(lambda l: l[0], path))
        pathy = list(map(lambda l: l[1], path))
        x, y = x[pathx], y[pathy]

        frames = x.shape[0]

        z = x - y
        s = np.sqrt((z * z).sum(-1)).sum()

        return (_logdb_const * float(s) / float(frames))

    def readmgc(self, audio_data):
        print("readmgc")
        x = self.util.change_audio_data_type_float_to_int(audio_data)
        if x.ndim == 2:
            x = x[:,1]
        frame_length = 1024
        hop_length = 256  
        # Windowing
        print("windowing")
        frames = librosa.util.frame(x, frame_length=frame_length, hop_length=hop_length).astype(np.float64).T
        frames *= pysptk.blackman(frame_length)
        assert frames.shape[1] == frame_length 
        # Order of mel-cepstrum
        order = 25
        alpha = 0.41
        stage = 5
        gamma = -1.0 / stage
        print("get mgcep")
        mgc = pysptk.mgcep(frames, order, alpha, gamma)
        mgc = mgc.reshape(-1, order + 1)
        return mgc