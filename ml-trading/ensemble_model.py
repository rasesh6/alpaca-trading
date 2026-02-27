"""
Ensemble Model for ML Trading
Combines Random Forest, XGBoost, and LightGBM
"""
import numpy as np
import pandas as pd
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report
from ml_config import ENSEMBLE_CONFIG, MODELS_DIR


class EnsembleModel:
    """Ensemble of RF, XGBoost, and LightGBM"""

    def __init__(self, config=None):
        self.config = config or ENSEMBLE_CONFIG
        self.rf_model = None
        self.xgb_model = None
        self.lgb_model = None
        self.is_fitted = False

    def build_models(self):
        """Build all models with configured parameters"""
        # Random Forest
        self.rf_model = RandomForestClassifier(
            n_estimators=self.config['rf_n_estimators'],
            max_depth=self.config['rf_max_depth'],
            min_samples_split=self.config['rf_min_samples_split'],
            min_samples_leaf=self.config['rf_min_samples_leaf'],
            n_jobs=-1,
            random_state=42
        )

        # XGBoost
        try:
            import xgboost as xgb
            self.xgb_model = xgb.XGBClassifier(
                n_estimators=self.config['xgb_n_estimators'],
                max_depth=self.config['xgb_max_depth'],
                learning_rate=self.config['xgb_learning_rate'],
                subsample=self.config['xgb_subsample'],
                colsample_bytree=self.config['xgb_colsample_bytree'],
                n_jobs=-1,
                random_state=42,
                use_label_encoder=False,
                eval_metric='mlogloss'
            )
        except ImportError:
            print("XGBoost not installed. Skipping XGBoost model.")
            self.xgb_model = None

        # LightGBM
        try:
            import lightgbm as lgb
            self.lgb_model = lgb.LGBMClassifier(
                n_estimators=self.config['lgb_n_estimators'],
                max_depth=self.config['lgb_max_depth'],
                learning_rate=self.config['lgb_learning_rate'],
                num_leaves=self.config['lgb_num_leaves'],
                n_jobs=-1,
                random_state=42,
                verbose=-1
            )
        except ImportError:
            print("LightGBM not installed. Skipping LightGBM model.")
            self.lgb_model = None

    def fit(self, X, y):
        """Train all models"""
        if self.rf_model is None:
            self.build_models()

        print("Training Random Forest...")
        self.rf_model.fit(X, y)
        rf_acc = accuracy_score(y, self.rf_model.predict(X))
        print(f"  RF Accuracy: {rf_acc:.4f}")

        if self.xgb_model is not None:
            print("Training XGBoost...")
            self.xgb_model.fit(X, y)
            xgb_acc = accuracy_score(y, self.xgb_model.predict(X))
            print(f"  XGB Accuracy: {xgb_acc:.4f}")

        if self.lgb_model is not None:
            print("Training LightGBM...")
            self.lgb_model.fit(X, y)
            lgb_acc = accuracy_score(y, self.lgb_model.predict(X))
            print(f"  LGB Accuracy: {lgb_acc:.4f}")

        self.is_fitted = True

    def predict_proba(self, X):
        """Get weighted probability predictions from ensemble"""
        if not self.is_fitted:
            raise ValueError("Model not fitted. Call fit() first.")

        # Get predictions from each model
        rf_proba = self.rf_model.predict_proba(X)

        # Weighted average
        weights = {'rf': self.config['rf_weight']}
        total_weight = weights['rf']

        if self.xgb_model is not None:
            xgb_proba = self.xgb_model.predict_proba(X)
            weights['xgb'] = self.config['xgb_weight']
            total_weight += weights['xgb']
        else:
            xgb_proba = None

        if self.lgb_model is not None:
            lgb_proba = self.lgb_model.predict_proba(X)
            weights['lgb'] = self.config['lgb_weight']
            total_weight += weights['lgb']
        else:
            lgb_proba = None

        # Normalize weights
        for key in weights:
            weights[key] /= total_weight

        # Weighted ensemble
        ensemble_proba = weights['rf'] * rf_proba
        if xgb_proba is not None:
            ensemble_proba += weights['xgb'] * xgb_proba
        if lgb_proba is not None:
            ensemble_proba += weights['lgb'] * lgb_proba

        return ensemble_proba

    def predict(self, X):
        """Get class predictions"""
        proba = self.predict_proba(X)
        classes = self.rf_model.classes_
        return classes[np.argmax(proba, axis=1)]

    def get_feature_importance(self, feature_names):
        """Get aggregated feature importance"""
        importance = {}

        # RF importance
        rf_imp = self.rf_model.feature_importances_
        for name, imp in zip(feature_names, rf_imp):
            importance[name] = imp * self.config['rf_weight']

        # XGB importance
        if self.xgb_model is not None:
            xgb_imp = self.xgb_model.feature_importances_
            for name, imp in zip(feature_names, xgb_imp):
                importance[name] = importance.get(name, 0) + imp * self.config['xgb_weight']

        # LGB importance
        if self.lgb_model is not None:
            lgb_imp = self.lgb_model.feature_importances_
            for name, imp in zip(feature_names, lgb_imp):
                importance[name] = importance.get(name, 0) + imp * self.config['lgb_weight']

        # Sort by importance
        return dict(sorted(importance.items(), key=lambda x: x[1], reverse=True))

    def save(self, name='ensemble_model'):
        """Save models to disk"""
        os.makedirs(MODELS_DIR, exist_ok=True)

        if self.rf_model:
            joblib.dump(self.rf_model, os.path.join(MODELS_DIR, f'{name}_rf.pkl'))
        if self.xgb_model:
            joblib.dump(self.xgb_model, os.path.join(MODELS_DIR, f'{name}_xgb.pkl'))
        if self.lgb_model:
            joblib.dump(self.lgb_model, os.path.join(MODELS_DIR, f'{name}_lgb.pkl'))

        print(f"Models saved to {MODELS_DIR}")

    def load(self, name='ensemble_model'):
        """Load models from disk"""
        rf_path = os.path.join(MODELS_DIR, f'{name}_rf.pkl')
        xgb_path = os.path.join(MODELS_DIR, f'{name}_xgb.pkl')
        lgb_path = os.path.join(MODELS_DIR, f'{name}_lgb.pkl')

        if os.path.exists(rf_path):
            self.rf_model = joblib.load(rf_path)
        if os.path.exists(xgb_path):
            self.xgb_model = joblib.load(xgb_path)
        if os.path.exists(lgb_path):
            self.lgb_model = joblib.load(lgb_path)

        self.is_fitted = True
        print(f"Models loaded from {MODELS_DIR}")
