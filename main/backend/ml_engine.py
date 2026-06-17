import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from datetime import datetime
from typing import Optional, List
import pickle
import os

class MLEngine:
    """ML engine for predicting wait times"""
    
    def __init__(self):
        self.model = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=5,
            min_samples_split=5,
            min_samples_leaf=2,
            random_state=42,
            subsample=0.8
        )
        self.scaler = StandardScaler()
        self.is_trained = False
        self.model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "palo_model.pkl")
        self.load_model()
    
    def load_model(self):
        """Load model from disk if available"""
        if os.path.exists(self.model_path):
            try:
                with open(self.model_path, "rb") as f:
                    self.model = pickle.load(f)
                    self.is_trained = True
            except Exception as e:
                print(f"Could not load model: {e}")
    
    def save_model(self):
        """Save model to disk"""
        try:
            with open(self.model_path, "wb") as f:
                pickle.dump(self.model, f)
        except Exception as e:
            print(f"Could not save model: {e}")
    
    def train(self, training_data: List[dict]):
        """
        Train the model on historical data
        
        Expected format:
        [
            {
                "hour_of_day": 9,
                "day_of_week": 1,
                "queue_depth": 5,
                "wait_time_minutes": 12.5
            },
            ...
        ]
        """
        if len(training_data) < 10:
            print("Insufficient training data (need at least 10 samples)")
            return False
        
        try:
            # Extract features and target
            features = []
            targets = []
            
            for sample in training_data:
                features.append([
                    sample["hour_of_day"],
                    sample["day_of_week"],
                    sample["queue_depth"]
                ])
                targets.append(sample["wait_time_minutes"])
            
            X = np.array(features)
            y = np.array(targets)
            
            # Scale features
            X_scaled = self.scaler.fit_transform(X)
            
            # Train model
            self.model.fit(X_scaled, y)
            self.is_trained = True
            
            # Save model
            self.save_model()
            
            print(f"Model trained on {len(training_data)} samples")
            return True
        except Exception as e:
            print(f"Training error: {e}")
            return False
    
    def predict(
        self,
        hour_of_day: int,
        day_of_week: int,
        queue_depth: int
    ) -> Optional[float]:
        """
        Predict wait time in minutes
        
        Args:
            hour_of_day: 0-23
            day_of_week: 0-6 (0=Monday)
            queue_depth: Number of people waiting
        
        Returns:
            Estimated wait time in minutes, or None if model not trained
        """
        if not self.is_trained:
            return None
        
        try:
            features = np.array([[hour_of_day, day_of_week, queue_depth]])
            features_scaled = self.scaler.transform(features)
            prediction = self.model.predict(features_scaled)[0]
            
            # Clamp to reasonable range (0-240 minutes)
            return max(0, min(240, float(prediction)))
        except Exception as e:
            print(f"Prediction error: {e}")
            return None
    
    def get_model_info(self) -> dict:
        """Get info about the trained model"""
        return {
            "is_trained": self.is_trained,
            "feature_importances": (
                self.model.feature_importances_.tolist() if self.is_trained else None
            ),
            "feature_names": ["hour_of_day", "day_of_week", "queue_depth"]
        }


# Global instance
ml_engine = MLEngine()
