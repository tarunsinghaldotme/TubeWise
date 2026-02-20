"""
conftest.py — Shared fixtures for TubeWise unit tests
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to sys.path so tests can import TubeWise modules
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def sample_raw_summary() -> str:
    """Realistic Claude output with all 8 expected sections."""
    return """\
### SUMMARY
This video explores the fundamentals of machine learning, covering supervised
and unsupervised learning approaches. The presenter explains key algorithms
and their real-world applications.

The discussion spans neural networks, decision trees, and ensemble methods.

### KEY_TAKEAWAYS
1. Supervised learning requires labeled data to train models
2. Neural networks can approximate any continuous function
3. Feature engineering is often more important than model selection
4. Cross-validation prevents overfitting on training data
5. Ensemble methods combine multiple models for better accuracy

### TOPICS_COVERED
- **Supervised Learning**: Training models on labeled datasets with known outputs. Includes classification and regression tasks.
- **Neural Networks**: Layered architectures inspired by the human brain. Deep learning uses many hidden layers.
- **Decision Trees**: Tree-structured models that split data on feature values. Easy to interpret but prone to overfitting.

### CONCEPT_EXPLANATIONS
- **Gradient Descent**: An optimization algorithm that iteratively adjusts model parameters to minimize a loss function. Think of it as rolling a ball downhill to find the lowest point.
- **Overfitting**: When a model learns noise in the training data rather than the underlying pattern. The model performs well on training data but poorly on new data.

### ACTION_ITEMS
- Set up a Python environment with scikit-learn
- Practice building a classification model on the Iris dataset
- Read the original backpropagation paper by Rumelhart et al.

### DIAGRAM_DESCRIPTION
```mermaid
graph TD
    A[Data Collection] --> B[Feature Engineering]
    B --> C{Choose Algorithm}
    C --> D[Supervised Learning]
    C --> E[Unsupervised Learning]
    D --> F[Model Training]
    E --> F
    F --> G[Evaluation]
    G --> H[Deployment]
```

### NOTABLE_QUOTES
- "All models are wrong, but some are useful"
- "The best model is the one you understand"
- "Data is the new oil, but only if you refine it"

### RESOURCES_MENTIONED
- **scikit-learn**: Python machine learning library with simple API
- **TensorFlow**: Google's deep learning framework for production
- **Kaggle**: Platform for data science competitions and datasets
"""


@pytest.fixture
def sample_transcript_entries() -> list[dict]:
    """Transcript entries in dict format, as returned by youtube-transcript-api."""
    return [
        {"text": "Welcome to today's video.", "start": 0.0, "duration": 2.5},
        {"text": "We'll cover machine learning basics.", "start": 2.5, "duration": 3.0},
        {"text": "Let's start with supervised learning.", "start": 5.5, "duration": 2.8},
        {"text": "Thank you for watching!", "start": 590.0, "duration": 2.0},
    ]
