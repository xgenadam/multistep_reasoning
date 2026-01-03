from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch


class BooleanDecider:
    def __init__(self, model_path):
        self.tokenizer = AutoTokenizer.from_pretrained(model_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(
            model_path
        ) #.cuda()

    def get_confidences(self, question: str) -> tuple[float, float]:
        inputs = self.tokenizer(
            question, return_tensors="pt", truncation=True, padding=True
        ).to(self.model.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=-1).tolist()[0]
            # no prob, yes prob
            return probs[0], probs[1]

    def get_decision(self, question) -> bool:
        no_prob, yes_prob = self.get_confidences(question)
        return yes_prob > no_prob
