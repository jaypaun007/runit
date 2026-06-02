import os
import sys
import shutil


def is_kaggle() -> bool:
    return bool(os.environ.get("KAGGLE_KERNEL_RUN_TYPE")) or os.path.exists("/kaggle")


def is_colab() -> bool:
    try:
        import google.colab  # type: ignore
        return True
    except ImportError:
        return "COLAB_GPU" in os.environ or "COLAB_TPU_ADDR" in os.environ
    except Exception:
        return False


def is_notebook_env() -> bool:
    return is_kaggle() or is_colab()


def has_docker() -> bool:
    return shutil.which("docker") is not None


def has_git() -> bool:
    return shutil.which("git") is not None


def has_npm() -> bool:
    return shutil.which("npm") is not None


def env_info() -> dict:
    info = {
        "platform": sys.platform,
        "python": sys.version,
        "is_kaggle": is_kaggle(),
        "is_colab": is_colab(),
        "has_docker": has_docker(),
        "has_git": has_git(),
        "has_npm": has_npm(),
        "cwd": os.getcwd(),
    }
    return info


def detect_env() -> str:
    if is_kaggle():
        return "kaggle"
    if is_colab():
        return "colab"
    return "local"
