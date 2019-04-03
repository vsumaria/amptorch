import sys
import time
import torch
import torch.nn as nn
import numpy as np
from torch.utils.data import DataLoader
from data_preprocess import AtomsDataset, factorize_data, collate_amp
from amp.utilities import Logger
from amp.descriptor.gaussian import Gaussian
from nn_torch_bfgs import FullNN, train_model
import torch.optim as optim
import matplotlib.pyplot as plt

log = Logger("../benchmark_results/results-log.txt")
log_epoch = Logger("../benchmark_results/epoch-log.txt")

log(time.asctime())
# device=torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
device = "cpu"
filename = "../benchmark_dataset/water.extxyz"

log("-" * 50)
log("Filename: %s" % filename)

training_data = AtomsDataset(filename, descriptor=Gaussian())
unique_atoms, _, _, _ = factorize_data(training_data)
n_unique_atoms = len(unique_atoms)

batch_size = len(training_data)
log("Batch Size = %d" % batch_size)
validation_frac = 0

if validation_frac != 0:
    samplers = training_data.create_splits(training_data, validation_frac)
    dataset_size = {
        "train": (1.0 - validation_frac) * len(training_data),
        "val": validation_frac * len(training_data),
    }

    log(
        "Training Data = %d Validation Data = %d"
        % (dataset_size["train"], dataset_size["val"])
    )

    atoms_dataloader = {
        x: DataLoader(
            training_data,
            batch_size,
            collate_fn=collate_amp,
            sampler=samplers[x],
        )
        for x in ["train", "val"]
    }

else:
    dataset_size = len(training_data)
    log("Training Data = %d" % dataset_size)
    atoms_dataloader = DataLoader(
        training_data, batch_size, collate_fn=collate_amp, shuffle=False
    )
model = FullNN(unique_atoms, batch_size)
# if torch.cuda.device_count()>1:
# print('Utilizing',torch.cuda.device_count(),'GPUs!')
# model=nn.DataParallel(model)
model = model.to(device)
criterion = nn.MSELoss()
log("Loss Function: %s" % criterion)

# Define the optimizer and implement any optimization settings
optimizer_ft = optim.LBFGS(model.parameters(), 1, max_iter=20)
# optimizer_ft=optim.LBFGS(model.parameters(),.8,max_iter=20,max_eval=100000,tolerance_grad=1e-8,tolerance_change=1e-6)

log("Optimizer Info:\n %s" % optimizer_ft)

# Define scheduler search strategies
# exp_lr_scheduler=lr_scheduler.StepLR(optimizer_ft,step_size=20,gamma=0.1)
# log('LR Scheduler Info: \n Step Size = %s \n Gamma = %s'%(exp_lr_scheduler.step_size,exp_lr_scheduler.gamma))

num_epochs = 20
log("Number of Epochs = %d" % num_epochs)
log("")
model = train_model(
    model,
    unique_atoms,
    dataset_size,
    criterion,
    optimizer_ft,
    atoms_dataloader,
    num_epochs,
)
torch.save(model.state_dict(), "../benchmark_results/benchmark_model.pt")


def parity_plot(training_data):
    loader = DataLoader(training_data, 400,
                        collate_fn=collate_amp, shuffle=False)
    model = FullNN(unique_atoms, 400)
    model.load_state_dict(torch.load(
        "../benchmark_results/benchmark_model.pt"))
    model.eval()
    predictions = []
    targets = []
    # device='cuda:0'
    device = "cpu"
    model = model.to(device)
    with torch.no_grad():
        for sample in loader:
            inputs = sample[0]
            for element in unique_atoms:
                inputs[element][0] = inputs[element][0].to(device)
            targets = sample[1]
            targets = targets.to(device)
            predictions = model(inputs)
        data_max = max(targets)
        data_min = min(targets)
        data_mean = torch.mean(targets)
        data_sd = torch.std(targets, dim=0)
        scale = (predictions * data_sd) + data_mean
        # scale=(predictions*(data_max-data_min))+data_min
        targets = targets.reshape(len(targets), 1)
        # scaled_pred=scaled_pred.reshape(len(targets),1)
        crit = nn.MSELoss()
        loss = crit(scale, targets)
        loss = loss / len(unique_atoms) ** 2
        loss = loss.detach().numpy()
        RMSE = np.sqrt(loss)
        print RMSE
        fig = plt.figure(figsize=(7.0, 7.0))
        ax = fig.add_subplot(111)
        targets = targets.detach().numpy()
        scale = scale.detach().numpy()
        ax.plot(targets, scale, "bo", markersize=3)
        ax.plot([data_min, data_max], [data_min, data_max], "r-", lw=0.3)
        ax.set_xlabel("ab initio energy, eV")
        ax.set_ylabel("PyTorch energy, eV")
        ax.set_title("Energies")
        fig.savefig("../benchmark_results/Plots/PyTorch_Prelims.pdf")
    plt.show()


def plot_hist(training_data):
    loader = DataLoader(
        training_data, 1, collate_fn=collate_amp, shuffle=False)
    model = FullNN(unique_atoms, 1)
    model.load_state_dict(torch.load("benchmark_results/benchmark_model.pt"))
    model.eval()
    predictions = []
    scaled_pred = []
    targets = []
    residuals = []
    # device='cuda:0'
    device = "cpu"
    model = model.to(device)
    for sample in loader:
        inputs = sample[0]
        for element in unique_atoms:
            inputs[element][0] = inputs[element][0].to(device)
        target = sample[1]
        target = target.to(device)
        prediction = model(inputs)
        predictions.append(prediction)
        targets.append(target)
    # data_max = max(targets)
    # data_min = min(targets)
    targets = torch.stack(targets)
    data_mean = torch.mean(targets)
    data_sd = torch.std(targets, dim=0)
    for index, value in enumerate(predictions):
        # scaled_value=(value*(data_max-data_min))+data_min
        scaled_value = (value * data_sd) + data_mean
        scaled_pred.append(scaled_value)
        residual = targets[index] - scaled_value
        residuals.append(residual)
    fig = plt.figure(figsize=(7.0, 7.0))
    ax = fig.add_subplot(111)
    ax.plot(scaled_pred, residuals, "bo", markersize=3)
    ax.set_xlabel("PyTorch energy, eV")
    ax.set_ylabel("residual, eV")
    ax.set_title("Energies")
    fig.savefig("benchmark_results/Plots/PyTorch_Residuals.pdf")
    # plt.show()


# parity_plot(training_data)
# plot_hist(training_data)