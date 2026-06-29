# Beginner's Guide to omyfish-python Codebase (pre-refactor)

**Welcome!** This guide assumes you're new to this project. No experience needed—just curiosity!

---

## 🎯 What is This Project?

**In plain English:** This project is a **fish classifier**—it's like a photo app that can look at a picture of a fish and tell you what species it is. Think of it like Shazam, but for fish! 📸🐟

The project has:
- A **machine learning model** (the "brain" that identifies fish)
- **Training code** (teaches the brain from examples)
- **Apps** (user-friendly ways to use it)

---

## 📂 Project Structure Explained Simply

Think of your project like a kitchen:

```
omyfish/                    ← Your main kitchen
├── configs/               ← Recipe cards (settings)
├── data/                  ← Ingredients (fish photos)
├── src/                   ← Cooking instructions (code that does work)
├── app/                   ← The restaurant (user interfaces)
├── checkpoints/           ← Leftovers saved in the fridge (trained models)
├── notebooks/             ← Your cooking journal (experiments)
├── CLAUDE.md              ← Advanced cooking notes
└── requirements.txt       ← Shopping list
```

**Key folders you'll care about:**

| Folder | What's Inside | Why Care? |
|--------|---------------|-----------|
| `configs/` | Settings file (`config.yaml`) | "Recipes" for how to train |
| `data/` | Fish photos + metadata | The actual photos being classified |
| `src/` | The actual code that does work | The "brain" logic |
| `app/` | User interfaces (Streamlit, FastAPI) | How humans interact with the AI |

---

## 🧭 Step-by-Step: How to Read This Codebase

### **Week 1: Understand the BIG PICTURE**

#### Day 1: Read the Overview
**Goal:** Know what this project does (30 minutes)

1. Open [README.md](README.md)
   - Just skim it—don't read every word
   - Get a sense of: "What problem does this solve?"
   - Look for commands like `make train`, `make app`, etc.

2. Open [CLAUDE.md](CLAUDE.md)
   - This is like a "cheat sheet" for the whole project
   - Read the "Architecture" section
   - **You don't need to understand everything—just get the overview**

**Checkpoint:** Can you answer this? *"What does this project do in 1 sentence?"*

---

#### Day 2: Look at the File Tree
**Goal:** Know what EACH file does (1 hour)

Open each of these files and just **read the first 20 lines** (not the whole thing!):

1. **[configs/config.yaml](configs/config.yaml)**
   - This is like a settings file
   - Shows: What backbone model? Image size? How long to train?
   - **You don't need to change anything yet—just see it exists**

2. **[data/metadata/fish_info.json](data/metadata/fish_info.json)**
   - Lists all the fish species this project knows about
   - Shows: Species name, conservation status, description
   - **Example:** What fish are in the dataset? Check here!

3. **[requirements.txt](requirements.txt)**
   - This is a shopping list: all the Python libraries you need
   - Examples: `torch`, `timm`, `streamlit`
   - **What to know:** If you run `pip install -r requirements.txt`, you get all these

**Checkpoint:** Can you answer this? *"What Python library is used for the AI model?"* (Hint: Look for `torch` or `tensorflow`)

---

#### Day 3-7: Map the File Dependencies
**Goal:** See how files connect to each other

```
Think of it like a movie script:
- WHO appears in the story? (Classes, functions)
- WHAT do they do? (Their purpose)
- WHERE do they get used? (Other files that import them)
```

**Start here (read in this order):**

1. **[src/model.py](src/model.py)** (15 min)
   - This is the "AI brain"
   - Contains: `FishClassifier` class
   - What it does: Takes an image → outputs predictions
   - **Don't worry about every line—just understand the flow**

2. **[src/dataset.py](src/dataset.py)** (15 min)
   - This loads fish photos from your hard drive
   - Contains: `FishDataset` class
   - What it does: Takes folder of fish photos → makes them ready for training
   - **Key question to ask:** How does it handle class imbalance?

3. **[src/transforms.py](src/transforms.py)** (10 min)
   - This is "data decoration"—flipping images, adjusting brightness, etc.
   - Why? So the model learns to recognize fish even in bad lighting
   - **Just see:** RandomFog, GaussianBlur, normalization

---

### **Week 2: Understand the WORKFLOW**

#### Day 8: The Training Pipeline
**Goal:** Understand how the model learns (1.5 hours)

**Read [src/train.py](src/train.py):**

Start at the top and find these sections:
1. **Imports** — What libraries are being used?
2. **Main training function** — What's the overall flow?
3. **Key concepts to spot:**
   - `WeightedRandomSampler` — Handles imbalanced classes (some fish have fewer photos)
   - `mixed precision training` — Makes training faster
   - `checkpointing` — Saves the best model

**Here's what happens in training (simplified):**

```
Step 1: Load config (CLAUDE.md explains this)
Step 2: Load dataset (fish photos from data/raw/)
Step 3: Create model (the FishClassifier)
Step 4: Loop 100 times (each time called an "epoch"):
   a) Feed photos to model
   b) Model makes predictions
   c) Compare predictions to correct answers
   d) Model learns from mistakes
   e) Save if this is the best version so far
Step 5: Save final model to checkpoints/best.pt
```

**Checkpoint:** Can you answer? *"Why do we need a WeightedRandomSampler?"*

---

#### Day 9: The Inference Pipeline
**Goal:** Understand how the model makes predictions (1 hour)

**Read [src/predict.py](src/predict.py):**

Look for the `FishPredictor` class. It does this:

```
Input: A fish photo
   ↓
Load the saved model (best.pt)
   ↓
Resize & normalize the photo
   ↓
Pass through model
   ↓
Get confidence scores for each species
   ↓
Return top-3 guesses with confidence %
   ↓
Output: "This is 85% sure it's a goldfish"
```

**Key thing to understand:**
- Training = Teaching the model
- Inference = Using the model to make predictions

---

#### Day 10: How Your Model Evaluates Itself
**Goal:** Understand how we measure success (45 min)

**Read [src/evaluate.py](src/evaluate.py):**

This asks questions like:
- "How many fish did we identify correctly?"
- "Which species are we bad at identifying?"
- "Which species are we good at?"

**Output:** A confusion matrix (fancy grid showing what we got right/wrong)

**Checkpoint:** Can you answer? *"How do you know if your model is good?"*

---

### **Week 3: The User Interfaces (Apps)**

#### Day 11: The Web App
**Goal:** See how real people use your model (1 hour)

**Read [app/main.py](app/main.py):**

This is **Streamlit**—a way to make web apps without knowing web development.

**What it does:**
1. User uploads a fish photo
2. Model predicts the species
3. Displays the result with pretty graphics and conservation info

**Key thing:** This file imports `FishPredictor` from `src/predict.py`
- So it's using the trained model!

**Try it:**
```bash
make app
# Then open browser to http://localhost:8501
```

---

#### Day 12: The API (For Developers)
**Goal:** See how to use the model programmatically (45 min)

**Read [app/api.py](app/api.py):**

This is for developers who want to use your model without the fancy web interface.

**What it does:**
1. Creates an endpoint: `POST /predict`
2. You send a fish photo
3. It returns JSON with predictions

**Example use:**
```bash
curl -F "image=@fish.jpg" http://localhost:8000/predict
# Returns: {"predictions": [{"species": "goldfish", "confidence": 0.85}]}
```

---

## 🎓 Understanding Concepts

### "What's a model?"
Think of a model like a trained expert:
- You show the expert lots and lots of fish photos
- They learn patterns: "Goldfish have these colors and shapes"
- Later, you show them a new photo: "Is this a goldfish?"
- They say: "Yes, 90% sure!"

In ML terms: A model is mathematical functions that learned from examples.

---

### "What's training?"
Training is **learning from examples**:

```
Before training:
- Model is random (like a baby who's never seen fish)

During training (100 epochs):
- Show 1000 fish photos
- Model makes guesses
- We tell it: "Wrong! That was a tuna, not a goldfish"
- Model adjusts its brain slightly
- Repeat 100 times

After training:
- Model is expert (like a marine biologist)
```

---

### "What's overfitting?"
**Problem:** Model memorizes the training photos instead of learning patterns.

**Example:**
- Trained on: 100 photos of goldfish from tank A
- Test on: Photos of goldfish from tank B
- Model fails! Why? It learned "tank A colors" not "goldfish features"

**Solution:** We use `WeightedRandomSampler` and augmentation!

---

### "What's augmentation?"
Augmentation = **artificially creating more training data by changing images slightly**:

```
Original photo: [a goldfish]
   ↓ Flip horizontally
Augmented: [goldfish flipped]
   ↓ Add fog (water murk)
Augmented: [goldfish in foggy water]
   ↓ Blur slightly
Augmented: [slightly blurry goldfish]
```

Why? Model learns: "Goldfish is goldfish, even with variations!"

See this in [src/transforms.py](src/transforms.py)

---

## 🚀 Quick Start: Actually Running Things

### Run Training
```bash
# Step 1: Put fish photos in data/raw/<species_name>/
# Step 2: Run:
make train

# What happens:
# 1. Loads photos from data/raw/
# 2. Creates model (FishClassifier)
# 3. Trains for 100 epochs (configured in config.yaml)
# 4. Saves best.pt to checkpoints/
```

### Make a Prediction
```bash
make predict IMAGE=path/to/your_fish.jpg

# What happens:
# 1. Loads best.pt
# 2. Resizes your photo
# 3. Runs inference
# 4. Prints: "This is 92% sure it's a tuna"
```

### Launch the Web App
```bash
make app
# Opens: http://localhost:8501
# Now upload fish photos through the UI
```

---

## 📋 Reading Checklist

- [ ] **Week 1, Day 1:** Read README.md and CLAUDE.md overview
- [ ] **Week 1, Day 2:** Skim configs/config.yaml, data/metadata/fish_info.json, requirements.txt
- [ ] **Week 1, Days 3-7:** Read src/model.py, src/dataset.py, src/transforms.py
- [ ] **Week 2, Day 8:** Read src/train.py (understand training loop)
- [ ] **Week 2, Day 9:** Read src/predict.py (understand inference)
- [ ] **Week 2, Day 10:** Read src/evaluate.py (understand evaluation)
- [ ] **Week 3, Day 11:** Read app/main.py (understand Streamlit app)
- [ ] **Week 3, Day 12:** Read app/api.py (understand API)

---

## 🆘 "I'm Lost" — Quick Reference

**Q: Which file controls training?**
A: [src/train.py](src/train.py)

**Q: Which file makes predictions?**
A: [src/predict.py](src/predict.py)

**Q: Where are settings?**
A: [configs/config.yaml](configs/config.yaml)

**Q: How do users interact with this?**
A: [app/main.py](app/main.py) (Streamlit) or [app/api.py](app/api.py) (API)

**Q: What's the model architecture?**
A: [src/model.py](src/model.py)

**Q: Where's the data loaded?**
A: [src/dataset.py](src/dataset.py)

---

## 🎉 Next Steps After Reading

1. **Run a quick prediction:** `make predict IMAGE=your_fish.jpg`
2. **Launch the app:** `make app`
3. **Try modifying config.yaml:** Change `batch_size: 32` to `16` and retrain
4. **Read the code comments:** Real files have comments explaining the "why"

---

**Remember:** Everyone started as a beginner. Take your time, and don't worry if you don't understand everything on first read. That's normal! 🐟
