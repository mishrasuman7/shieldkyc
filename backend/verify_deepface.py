# verify_deepface.py — throwaway check that DeepFace + tf-keras work.
# Run once, confirm it prints SUCCESS, then you can delete it.

# These two lines just quiet TensorFlow's very noisy startup logs.
# They must come BEFORE importing anything tensorflow-related.
import os
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"      # hide info/warning spam
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"     # silence the oneDNN notice

print("Importing DeepFace (this triggers TensorFlow — may take 10-30s)...")
from deepface import DeepFace   # if tf-keras were missing, this line would throw

print("Loading the ArcFace model (downloads ~100MB on first run)...")
model = DeepFace.build_model("ArcFace")

print("\n" + "=" * 45)
print("  SUCCESS — DeepFace + ArcFace are working.")
print("  TensorFlow:", __import__("tensorflow").__version__)
print("=" * 45)