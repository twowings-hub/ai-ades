"""
AI-ADES LSTM-Autoencoder (Phase 6)

Plasma 센서 시계열의 정상 가공 패턴을 재구성하도록 학습한 뒤,
재구성 오차(reconstruction error)가 임계값을 넘는 구간을 이상(anomaly)으로 판정한다.

목표: 이상감지 F1 >= 0.80 (개발플랜 Phase 6)
"""
import numpy as np
import torch
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

WINDOW_SIZE = 50  # 시계열 윈도우 길이 (샘플 수)
STRIDE = 10  # 윈도우 슬라이딩 간격
HIDDEN_SIZE = 16
N_LAYERS = 1
RANDOM_STATE = 42

# 재구성 오차 임계값 = 학습 데이터 오차 분포의 백분위수
THRESHOLD_PERCENTILE = 95


class LSTMAutoencoder(nn.Module):
    """LSTM 인코더로 시퀀스를 압축하고, LSTM 디코더로 원본 시퀀스를 재구성한다."""

    def __init__(self, n_channels: int, hidden_size: int = HIDDEN_SIZE, n_layers: int = N_LAYERS):
        super().__init__()
        self.window_size = WINDOW_SIZE
        self.encoder = nn.LSTM(
            input_size=n_channels, hidden_size=hidden_size, num_layers=n_layers, batch_first=True
        )
        self.decoder = nn.LSTM(
            input_size=hidden_size, hidden_size=hidden_size, num_layers=n_layers, batch_first=True
        )
        self.output_layer = nn.Linear(hidden_size, n_channels)

    def forward(self, x):
        # x: (batch, window_size, n_channels)
        _, (hidden, _) = self.encoder(x)
        latent = hidden[-1]  # (batch, hidden_size) — 마지막 레이어의 은닉 상태

        # 디코더 입력: latent 벡터를 시퀀스 길이만큼 반복
        decoder_input = latent.unsqueeze(1).repeat(1, x.size(1), 1)
        decoded, _ = self.decoder(decoder_input)

        return self.output_layer(decoded)


def make_windows(arr: np.ndarray, window_size: int = WINDOW_SIZE, stride: int = STRIDE) -> np.ndarray:
    """
    (n_samples, n_channels) 배열을 (n_windows, window_size, n_channels) 윈도우로 슬라이싱한다.
    n_samples < window_size이면 빈 배열을 반환한다.
    """
    n_samples, n_channels = arr.shape
    if n_samples < window_size:
        return np.empty((0, window_size, n_channels), dtype=np.float32)

    windows = [
        arr[start : start + window_size]
        for start in range(0, n_samples - window_size + 1, stride)
    ]
    return np.stack(windows).astype(np.float32)


def train_autoencoder(
    windows: np.ndarray,
    epochs: int = 20,
    batch_size: int = 32,
    lr: float = 1e-3,
) -> tuple[LSTMAutoencoder, StandardScaler, float, dict]:
    """
    정상 데이터로 LSTM-Autoencoder를 학습한다.

    Args:
        windows: (n_windows, window_size, n_channels) 정상 데이터 윈도우
        epochs: 학습 epoch 수
        batch_size: 배치 크기
        lr: 학습률

    Returns:
        (학습된 모델, 채널별 StandardScaler, 이상감지 임계값, 학습 metrics)
    """
    if len(windows) == 0:
        raise ValueError("학습 데이터(windows)가 비어 있습니다")

    torch.manual_seed(RANDOM_STATE)

    n_windows, window_size, n_channels = windows.shape

    # 채널별 정규화 (window/sample 축을 합쳐서 fit)
    scaler = StandardScaler()
    flat = windows.reshape(-1, n_channels)
    scaler.fit(flat)
    normalized = scaler.transform(flat).reshape(n_windows, window_size, n_channels).astype(np.float32)

    dataset = TensorDataset(torch.from_numpy(normalized))
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True)

    model = LSTMAutoencoder(n_channels=n_channels)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    model.train()
    loss_history = []
    for _ in range(epochs):
        epoch_losses = []
        for (batch,) in loader:
            optimizer.zero_grad()
            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()
            epoch_losses.append(loss.item())
        loss_history.append(float(np.mean(epoch_losses)))

    # 학습 데이터 재구성 오차 분포로 임계값 산출
    train_errors = compute_reconstruction_error(model, normalized, scaler=None)
    threshold = float(np.percentile(train_errors, THRESHOLD_PERCENTILE))

    metrics = {
        "final_loss": loss_history[-1],
        "loss_history": loss_history,
        "threshold": threshold,
        "n_windows": n_windows,
    }

    return model, scaler, threshold, metrics


def compute_reconstruction_error(
    model: LSTMAutoencoder, windows: np.ndarray, scaler: StandardScaler | None
) -> np.ndarray:
    """
    윈도우별 재구성 오차(MSE, window/channel 평균)를 계산한다.

    Args:
        model: 학습된 LSTMAutoencoder
        windows: (n_windows, window_size, n_channels) — scaler가 주어지면 원본 스케일로 간주
        scaler: None이면 windows가 이미 정규화된 것으로 간주

    Returns:
        (n_windows,) 윈도우별 평균 MSE
    """
    if len(windows) == 0:
        return np.empty((0,), dtype=np.float32)

    if scaler is not None:
        n_windows, window_size, n_channels = windows.shape
        flat = windows.reshape(-1, n_channels)
        windows = scaler.transform(flat).reshape(n_windows, window_size, n_channels).astype(np.float32)

    model.eval()
    with torch.no_grad():
        x = torch.from_numpy(windows.astype(np.float32))
        reconstructed = model(x)
        errors = torch.mean((reconstructed - x) ** 2, dim=(1, 2))

    return errors.numpy()


def detect_anomalies(errors: np.ndarray, threshold: float) -> np.ndarray:
    """재구성 오차가 임계값을 초과하는 윈도우를 이상(anomaly)으로 판정한다."""
    return errors > threshold


def evaluate_anomaly_detection(errors: np.ndarray, threshold: float, labels: np.ndarray) -> dict:
    """
    레이블(0=정상, 1=이상)이 있는 경우 F1/precision/recall을 계산한다.
    목표: F1 >= 0.80 (개발플랜 Phase 6 완료 기준)

    Args:
        errors: 윈도우별 재구성 오차
        threshold: 이상감지 임계값
        labels: 윈도우별 실제 레이블 (0/1)

    Returns:
        {"f1": ..., "precision": ..., "recall": ...}
    """
    preds = detect_anomalies(errors, threshold).astype(int)
    return {
        "f1": float(f1_score(labels, preds, zero_division=0)),
        "precision": float(precision_score(labels, preds, zero_division=0)),
        "recall": float(recall_score(labels, preds, zero_division=0)),
    }
