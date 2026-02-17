import joblib
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

class ProbabilityModel:

    def __init__(self):
        self.model = LogisticRegression()
        self.scaler = StandardScaler()
        self.trained = False

    def train(self, X, y):
        X_scaled = self.scaler.fit_transform(X)
        self.model.fit(X_scaled, y)
        self.trained = True

    def predict_proba(self, X):
        if not self.trained:
            raise Exception("Model not trained")
        X_scaled = self.scaler.transform(X)
        return self.model.predict_proba(X_scaled)[:, 1]

    def save(self, path):
        joblib.dump((self.model, self.scaler), path)

    def load(self, path):
        self.model, self.scaler = joblib.load(path)
        self.trained = True
