#!/usr/bin/env python3
"""
Test script to compare basic vs enhanced preprocessing
"""

import os
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.llm.openai_client import OpenAIClient
from app.utils.similarity import cosine_similarity, normalize_query
from app.utils.config import get_settings

def test_query_pair(query1: str, query2: str, enhanced: bool = True):
    """Test similarity between two queries with different preprocessing"""
    settings = get_settings()
    
    openai_client = OpenAIClient(
        api_key=settings.openai_api_key,
        max_llm_calls=100,
        redis_client=None,
        system_prompt="",
        fallback_response="",
        embedding_model="text-embedding-3-small",
    )
    
    # Normalize queries
    norm1 = normalize_query(query1, enhanced=enhanced)
    norm2 = normalize_query(query2, enhanced=enhanced)
    
    # Generate embeddings
    emb1 = openai_client.get_embedding(norm1)
    emb2 = openai_client.get_embedding(norm2)
    
    # Calculate similarity
    similarity = cosine_similarity(emb1, emb2)
    
    return {
        "query1": query1,
        "query2": query2,
        "normalized1": norm1,
        "normalized2": norm2,
        "similarity": similarity,
        "enhanced": enhanced
    }

def main():
    load_dotenv()
    
    settings = get_settings()
    
    if not settings.openai_api_key:
        print("❌ ERROR: OPENAI_API_KEY not set")
        sys.exit(1)
    
    # Test pairs from the test suite
    test_pairs = [
        ("How do I change my password?", "I want to update my password"),
        ("How do I change my password?", "Reset my login credentials please"),
        ("How do I change my billing address?", "I want to update my payment method."),
        ("What is the capital city of France?", "Which city is the most populous and the seat of government in France?"),
    ]
    
    print("=" * 100)
    print("PREPROCESSING COMPARISON TEST")
    print("=" * 100)
    print()
    
    results = []
    
    for query1, query2 in test_pairs:
        print(f"Testing: '{query1}' vs '{query2}'")
        print("-" * 100)
        
        # Test with basic preprocessing
        basic_result = test_query_pair(query1, query2, enhanced=False)
        
        # Test with enhanced preprocessing
        enhanced_result = test_query_pair(query1, query2, enhanced=True)
        
        improvement = enhanced_result["similarity"] - basic_result["similarity"]
        
        print(f"Basic preprocessing:")
        print(f"  Normalized 1: {basic_result['normalized1']}")
        print(f"  Normalized 2: {basic_result['normalized2']}")
        print(f"  Similarity: {basic_result['similarity']:.4f}")
        print()
        print(f"Enhanced preprocessing:")
        print(f"  Normalized 1: {enhanced_result['normalized1']}")
        print(f"  Normalized 2: {enhanced_result['normalized2']}")
        print(f"  Similarity: {enhanced_result['similarity']:.4f}")
        print()
        print(f"Improvement: {improvement:+.4f} ({improvement*100:+.2f}%)")
        
        threshold = settings.similarity_threshold
        basic_hit = basic_result["similarity"] >= threshold
        enhanced_hit = enhanced_result["similarity"] >= threshold
        
        if not basic_hit and enhanced_hit:
            print(f"✅ Enhanced preprocessing enables cache hit! (threshold: {threshold})")
        elif basic_hit and enhanced_hit:
            print(f"✓ Both would hit cache")
        elif not basic_hit and not enhanced_hit:
            print(f"✗ Both would miss cache")
        else:
            print(f"⚠️  Basic would hit but enhanced would miss (unlikely)")
        
        print()
        print("=" * 100)
        print()
        
        results.append({
            "query1": query1,
            "query2": query2,
            "basic_similarity": basic_result["similarity"],
            "enhanced_similarity": enhanced_result["similarity"],
            "improvement": improvement,
            "basic_hit": basic_hit,
            "enhanced_hit": enhanced_hit,
        })
    
    # Summary
    print("SUMMARY")
    print("=" * 100)
    print()
    
    avg_improvement = sum(r["improvement"] for r in results) / len(results)
    hits_gained = sum(1 for r in results if not r["basic_hit"] and r["enhanced_hit"])
    
    print(f"Average similarity improvement: {avg_improvement:+.4f}")
    print(f"Cache hits gained: {hits_gained}/{len(results)}")
    print()
    
    print("Recommendation:")
    if avg_improvement > 0.02 and hits_gained > 0:
        print("✅ Enhanced preprocessing should improve cache hit rate")
    elif avg_improvement > 0:
        print("⚠️  Enhanced preprocessing provides marginal improvement")
    else:
        print("❌ Enhanced preprocessing does not improve similarity")

if __name__ == "__main__":
    main()
