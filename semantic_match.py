"""
Semantic matching module - lightweight alternative to sentence-transformers.
Uses TF-IDF for text similarity without heavy ML dependencies.
"""
import math
import re
from collections import Counter


def tokenize(text):
    """Simple tokenization for TF-IDF."""
    if not text:
        return []
    # Lowercase and split on non-alphanumeric
    tokens = re.findall(r'\b[a-z0-9+#]+\b', text.lower())
    # Remove very short tokens
    return [t for t in tokens if len(t) > 1]


def compute_tf(tokens):
    """Compute term frequency."""
    tf = Counter(tokens)
    total = len(tokens)
    if total == 0:
        return {}
    return {t: c / total for t, c in tf.items()}


def compute_idf(documents):
    """Compute inverse document frequency across documents."""
    n_docs = len(documents)
    if n_docs == 0:
        return {}

    # Count document frequency
    df = Counter()
    for doc in documents:
        unique_tokens = set(doc)
        for token in unique_tokens:
            df[token] += 1

    # IDF with smoothing
    idf = {}
    for token, freq in df.items():
        idf[token] = math.log((1 + n_docs) / (1 + freq)) + 1

    return idf


def tfidf_vector(tokens, idf):
    """Compute TF-IDF vector."""
    tf = compute_tf(tokens)
    return {t: tf.get(t, 0) * idf.get(t, 0) for t in tf}


def cosine_similarity(vec1, vec2):
    """Compute cosine similarity between two vectors."""
    if not vec1 or not vec2:
        return 0.0

    # Common keys
    common = set(vec1.keys()) & set(vec2.keys())
    if not common:
        return 0.0

    dot = sum(vec1[k] * vec2[k] for k in common)
    norm1 = math.sqrt(sum(v * v for v in vec1.values()))
    norm2 = math.sqrt(sum(v * v for v in vec2.values()))

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot / (norm1 * norm2)


def compute_semantic_similarity(resume_text, job_text):
    """
    Compute semantic similarity between resume and job description.
    Returns a score 0-100.
    """
    if not resume_text or not job_text:
        return 0

    resume_tokens = tokenize(resume_text)
    job_tokens = tokenize(job_text)

    if not resume_tokens or not job_tokens:
        return 0

    # Compute IDF on combined documents
    idf = compute_idf([resume_tokens, job_tokens])

    # Compute TF-IDF vectors
    resume_vec = tfidf_vector(resume_tokens, idf)
    job_vec = tfidf_vector(job_tokens, idf)

    # Compute similarity
    similarity = cosine_similarity(resume_vec, job_vec)

    # Scale to 0-100
    return int(similarity * 100)


def extract_matching_keywords(resume_text, job_text, top_n=10):
    """Extract top matching keywords between resume and job."""
    resume_tokens = set(tokenize(resume_text))
    job_tokens = set(tokenize(job_text))

    # Find intersection
    common = resume_tokens & job_tokens

    # Remove common stop words
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
                  'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
                  'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
                  'will', 'would', 'could', 'should', 'may', 'might', 'can', 'shall',
                  'we', 'you', 'they', 'it', 'he', 'she', 'i', 'me', 'my', 'your',
                  'our', 'their', 'this', 'that', 'these', 'those', 'not', 'no'}

    filtered = common - stop_words

    # Rank by frequency in job text
    job_freq = Counter(tokenize(job_text))
    ranked = sorted(filtered, key=lambda x: job_freq.get(x, 0), reverse=True)

    return ranked[:top_n]


if __name__ == "__main__":
    resume = """
    John Doe
    Skills: Python, Power Automate, RPA, SQL, Data Analysis
    Experience: Data Analyst at Acme Corp (10 months), RPA Intern at Acme Logistics
    Education: Diploma in Computer Science
    """

    job = """
    Junior RPA Developer
    Requirements: Python programming, Power Automate, UiPath experience preferred.
    Must have SQL skills. Entry level welcome. Fresh graduates encouraged to apply.
    """

    score = compute_semantic_similarity(resume, job)
    print(f"Semantic similarity: {score}/100")

    keywords = extract_matching_keywords(resume, job)
    print(f"Matching keywords: {keywords}")
