import os
import sys
sys.path.insert(0,os.getcwd())
import argparse
import importlib
import numpy as np
import torch
# import torch.backends.cudnn as cudnn
import torch.optim as optim
from torch.utils.data import DataLoader

import time
import copy

from utils.history import History
from utils.dataloader import Mydataset, collate
from utils.train_utils import train,validation,print_info, file2dict
from models.build import BuildNet
from core.optimizers import *

def parse_args():
    parser = argparse.ArgumentParser(description='Train a model')
    parser.add_argument('--config', default='../models/convnext/convnext_base.py', help='train config file path')
    args = parser.parse_args()
    return args

def main(): 
    args = parse_args()
    model_cfg,train_pipeline,val_pipeline,data_cfg,lr_config,optimizer_cfg = file2dict(args.config)
    dirname = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime())
    save_dir = os.path.join('../logs',model_cfg.get('backbone').get('type'),dirname)
    os.makedirs(save_dir)
    train_annotations   = "datas/train.txt"
    test_annotations    = 'datas/test.txt'
    
    train_history =History(save_dir)
    
    with open(train_annotations, encoding='utf-8') as f:
        train_datas = f.readlines()
    with open(test_annotations, encoding='utf-8') as f:
        val_datas   = f.readlines()
    
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = BuildNet(copy.deepcopy(model_cfg)).to(device)

    print_info(model_cfg)
    
    #if not data_cfg.get('train').get('pretrained_flag'):
    print('Initialize the weights.')
    model.init_weights()
        
    if data_cfg.get('train').get('pretrained_flag') and data_cfg.get('train').get('pretrained_weights'):
        print('Loading {}'.format(os.path.basename(data_cfg.get('train').get('pretrained_weights'))))
        model_dict = model.state_dict()
        pretrained_dict = torch.load(data_cfg.get('train').get('pretrained_weights'), map_location=device)
        if 'state_dict' in pretrained_dict:
            pretrained_dict = pretrained_dict['state_dict']       
        pretrained_dict = {k: v for k, v in pretrained_dict.items() if k in model_dict.keys() and np.shape(model_dict[k]) ==  np.shape(v) and 'backbone' in k}
        print(model.load_state_dict(pretrained_dict,strict=False))
        
    if data_cfg.get('train').get('freeze_flag') and data_cfg.get('train').get('freeze_layers'):
        freeze_layers = ' '.join(list(data_cfg.get('train').get('freeze_layers')))
        print('Freeze layers : ' + freeze_layers)
        model.freeze_layers(data_cfg.get('train').get('freeze_layers'))
    
    optimizer = eval('optim.' + optimizer_cfg.pop('type'))(params=model.parameters(),**optimizer_cfg) 
    lr_update_func = eval(lr_config.pop('type'))(**lr_config)
    
    train_dataset = Mydataset(train_datas, train_pipeline)
    val_dataset = Mydataset(val_datas, val_pipeline)

    train_loader = DataLoader(train_dataset, shuffle=True, batch_size=data_cfg.get('batch_size'), num_workers=data_cfg.get('num_workers'),pin_memory=True, drop_last=True, collate_fn=collate)
    val_loader = DataLoader(val_dataset, shuffle=False, batch_size=data_cfg.get('batch_size'), num_workers=data_cfg.get('num_workers'), pin_memory=True,
    drop_last=True, collate_fn=collate)
    
    runner = dict(
        optimizer         = optimizer,
        train_loader      = train_loader,
        val_loader        = val_loader,
        iter              = 0,
        epoch             = 100,
        max_epochs       = data_cfg.get('train').get('epoches'),
        max_iters         = data_cfg.get('train').get('epoches')*len(train_loader),
        best_train_loss   = float('INF'),
        best_val_acc     = float(0),
        best_train_weight = '',
        best_val_weight   = '',
        last_weight       = ''
    )
    
    lr_update_func.before_run(runner)
    
    for epoch in range(data_cfg.get('train').get('epoches')):
        runner['epoch'] = epoch
        lr_update_func.before_train_epoch(runner)
        train(model,runner, lr_update_func, device, epoch, data_cfg.get('train').get('epoches'), save_dir,train_history)
        validation(model,runner, data_cfg.get('test'), device, epoch, data_cfg.get('train').get('epoches'), save_dir,train_history)

        #torch.save(model.state_dict(), "./weights/model-{}.pth".format(epoch))

        train_history.after_epoch(epoch+1)


if __name__ == "__main__":
    main()
