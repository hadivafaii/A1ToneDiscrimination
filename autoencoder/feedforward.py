import torch
from torch import nn
from torch.nn import functional as F
from .model_utils import print_num_params
from .configuration import FeedForwardConfig


class TiedAutoEncoder(nn.Module):
    def __init__(self,
                 config: FeedForwardConfig,
                 verbose: bool = False,):
        super(TiedAutoEncoder, self).__init__()
        self.config = config
        self.embedding = CellEmbedding(config, verbose)
        self.encoder = nn.Linear(config.h_dim, config.z_dim, bias=True)
        self.decoder = nn.Linear(config.z_dim, config.h_dim, bias=True)
        self.relu1 = nn.ReLU(inplace=True)
        self.relu2 = nn.ReLU(inplace=True)
        self.relu3 = nn.ReLU(inplace=True)
        self.dropout = nn.Dropout(config.dropout)
        self.criterion = nn.MSELoss(reduction="sum")

        if verbose:
            print_num_params(self)

    def forward(self, name, x):
        x = self.embedding(name, x, encoding=True)
        x = self.relu1(x)
        x = self.dropout(x)
        x = self.encoder(x)
        z = self.relu2(x)
        y = self.decoder(z)
        y = self.relu3(y)
        y = self.embedding(name, y, encoding=False)
        return y, z


class Classifier(nn.Module):
    def __init__(self,
                 config: FeedForwardConfig,
                 verbose: bool = False,):
        super(Classifier, self).__init__()

        self.fc = nn.Linear(config.h_dim, config.c_dim, bias=True)
        self.relu = nn.ReLU(inplace=True)
        self.norm = nn.LayerNorm(config.c_dim)
        self.classifier = nn.Linear(config.c_dim, len(config.include_trials), bias=True)

        if verbose:
            print_num_params(self)

    def forward(self, x):
        # input shape: N x h_dim
        x = self.fc(x)  # N x c_dim
        x = self.relu(x)
        x = self.norm(x)
        y = self.classifier(x)  # N x num_classes
        return y


class CellEmbedding(nn.Module):
    def __init__(self,
                 config: FeedForwardConfig,
                 verbose=False,):
        super(CellEmbedding, self).__init__()

        self.layer = nn.ModuleDict(
            {name: nn.Linear(nc, config.h_dim, bias=False)
             for name, nc in config.nb_cells.items()}
        )
        self.decoder_bias = nn.ParameterDict(
            {name: nn.Parameter(torch.zeros(nc))
             for name, nc in config.nb_cells.items()}
        )
        if verbose:
            print_num_params(self)

    def forward(self, name, x, encoding: bool = True):
        weight = self.layer[name].weight
        bias = self.decoder_bias[name]
        return F.linear(x, weight, None) if encoding else F.linear(x, weight.T, bias)


class AutoEncoder(nn.Module):
    def __init__(self,
                 config,
                 nb_cells,
                 verbose=False,):
        super(AutoEncoder, self).__init__()

        self.encoder = FFEncoder(config, nb_cells, verbose)
        self.decoder = FFDecoder(config, nb_cells, verbose)
        self.criterion = nn.MSELoss(reduction="sum")

        if verbose:
            print_num_params(self)

    def forward(self, name, x):
        z = self.encoder(name, x)
        y = self.decoder(name, z)
        return z, y


class FFEncoder(nn.Module):
    def __init__(self,
                 config,
                 nb_cells,
                 verbose=False,):
        super(FFEncoder, self).__init__()

        self.fc1 = nn.ModuleDict(
            {
                name: nn.Linear(nc, config.h_dim, bias=True)
                for name, nc in nb_cells.items()
            }
        )
        self.fc2 = nn.Linear(config.h_dim, config.z_dim, bias=True)

        self.relu1 = nn.ReLU(inplace=True)
        self.relu2 = nn.ReLU(inplace=True)

        if verbose:
            print_num_params(self)

    def forward(self, name, x):
        x = self.fc1[name](x)
        x = self.relu1(x)
        x = self.fc2(x)
        x = self.relu2(x)
        return x


class FFDecoder(nn.Module):
    def __init__(self,
                 config,
                 nb_cells,
                 verbose=False,):
        super(FFDecoder, self).__init__()

        self.fc1 = nn.Linear(config.z_dim, config.h_dim, bias=True)
        self.fc2 = nn.ModuleDict(
            {
                name: nn.Linear(config.h_dim, nc, bias=True)
                for name, nc in nb_cells.items()
            }
        )
        self.relu = nn.ReLU(inplace=True)

        if verbose:
            print_num_params(self)

    def forward(self, name, x):
        x = self.fc1(x)
        x = self.relu(x)
        x = self.fc2[name](x)
        return x