text_data = "This is a Sample TEXT, with punctuation! and some common stop words."
import string
import nltk
from nltk.corpus import stopwords
nltk.download('stopwords')
def preprocess_text(text):
    text = text.lower()
    text = text.translate(str.maketrans('', '', string.punctuation))
    stop_words = set(stopwords.words('english'))
    words = text.split()
    filtered = [word for word in words if word not in stop_words]
    return " ".join(filtered)
processed_text = preprocess_text(text_data)
print("Original Text:")
print(text_data)
print("\nProcessed Text:")
print(processed_text)
