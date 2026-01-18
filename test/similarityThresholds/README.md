# Similarity Threshold & Embedding Model Testing Suite

This directory contains comprehensive testing tools for evaluating semantic caching performance across different similarity thresholds and embedding models.

## Overview

The testing suite provides a **comprehensive comparison** of embedding models and similarity thresholds:

**Comprehensive Test** (`test_comprehensive.py`)
- Tests ALL 3 embedding models × ALL 4 thresholds (12 total combinations)
- Uses consistent test methodology across all models
- Generates comprehensive comparison and recommendations
- Single unified test that provides complete analysis

**Models Tested**:
- `text-embedding-3-small` (cost-effective, recommended)
- `text-embedding-3-large` (highest performance)
- `text-embedding-ada-002` (legacy)

**Thresholds Tested**: 0.75, 0.80, 0.85, 0.90

## Quick Start

### Prerequisites

```bash
# Install dependencies
pip install redis requests matplotlib seaborn pandas

# Ensure Redis is running
docker compose up redis
```

### Running the Test

#### Quick Start

```bash
cd test/similarityThresholds
./run_threshold_tests.sh
```

#### Manual Execution

```bash
python3 test_comprehensive.py
```

This will:
- Test all 3 embedding models × all 4 thresholds (12 combinations)
- Use consistent test methodology for all models
- Generate comprehensive comparison
- Print detailed comparison tables
- Save results: `comprehensive_test_results_YYYYMMDD_HHMMSS.json`

**Expected Duration**: ~30-40 minutes (12 test combinations)

## File Structure

```
test/similarityThresholds/
├── README.md              # This file - overview and usage guide
├── CONCLUSIONS.md         # Analysis framework and recommendations
├── test_comprehensive.py  # Main comprehensive test script
├── run_threshold_tests.sh # Convenience script to run tests
└── comprehensive_test_results_*.json  # Generated test results (gitignored)
```

## Test Methodology

### Comprehensive Test Flow

**Purpose**: Complete comparison of all embedding models across all thresholds

**Test Structure**:
1. **For each embedding model** (3 models):
   - **For each threshold** (4 thresholds):
     - Clear cache (fresh start)
     - Populate cache with 12 base queries
     - Test semantic similarity with 12 test queries
     - Collect metrics (hit rate, acceptability, costs)
     - Store results

2. **After all 12 combinations complete**:
   - Calculate averages and totals per model
   - Compare models (accuracy, cost, false positives/negatives)
   - Identify best threshold per model
   - Generate recommendations

**Test Dataset**:
- **Base Queries** (12): Password, billing, account, features (cache population)
- **Test Queries** (12): 
  - Group A: 6 semantically equivalent (should hit)
  - Group B: 4 related but different (should miss)
  - Group C: 2 unrelated (should miss)

**Total Test Combinations**: 3 models × 4 thresholds = **12 test runs**

## Understanding Results

### Key Metrics

1. **Acceptability Rate** (Most Important)
   - Percentage of correct responses
   - Includes cache hits (if correct) and cache misses (always correct)
   - Should be >90% for production use

2. **Hit Rate**
   - Percentage of queries that hit cache
   - Higher = more cache usage = lower LLM costs
   - Must balance with accuracy

3. **False Positives**
   - Group B/C queries that incorrectly hit cache (wrong answer)
   - Lower is better (ideally 0)

4. **False Negatives**
   - Group A queries that incorrectly miss cache (missed opportunity)
   - Lower is better

5. **Cost**
   - Embedding cost: Cost of generating embeddings
   - LLM cost: Cost when cache misses
   - Total: Embedding + LLM costs

### Expected Behavior

**As Threshold Increases (0.75 → 0.90)**:
- Hit rate decreases (stricter matching)
- LLM calls increase (fewer cache hits)
- Acceptability increases (fewer false positives)
- Cost increases (more LLM calls)

**Model Comparison**:
- **3-small**: Best cost-effectiveness, good accuracy (92-95%)
- **3-large**: Highest accuracy (94-97%), but 6.5x more expensive
- **ada-002**: Lower accuracy (88-92%), higher cost than 3-small

## Recommendations

After running the comprehensive test, review the console output and JSON results to determine:

### Optimal Configuration

The test will recommend:
- **Best Model**: Based on accuracy and cost-effectiveness
- **Best Threshold**: Per model (typically 0.80-0.85)
- **Cost Analysis**: Total costs and savings per model

### Typical Findings

Based on the test framework:

**Recommended: text-embedding-3-small @ threshold 0.80-0.85**
- Best cost-performance ratio
- 92-95% acceptability rate
- 6.5x cheaper than 3-large

**Consider 3-large if**:
- Accuracy is critical (medical, legal, security)
- False positives are costly
- Budget allows premium pricing

See `CONCLUSIONS.md` for detailed analysis framework and update it with your actual results.

## Example Results Interpretation

### Threshold Test Results

```
Threshold  Hit Rate  Acceptability  LLM Calls  Cost    Savings
0.75       85.7%     75.0%          2          $0.02   $0.10
0.80       71.4%     85.7%          4          $0.04   $0.08
0.85       57.1%     92.9%          6          $0.06   $0.06
0.90       42.9%     100.0%         8          $0.08   $0.04
```

**Analysis**:
- Threshold 0.80-0.85 provides best balance
- Acceptability jumps significantly from 0.75 to 0.80
- Cost increases linearly with threshold
- Recommendation: **0.80 or 0.85** depending on accuracy requirements

### Model Comparison Results

```
Model                    Acceptability  FP  FN  Embed Cost
text-embedding-3-small   92.9%         1   0   $0.000012
text-embedding-3-large   96.4%         0   0   $0.000078
text-embedding-ada-002   89.3%         2   1   $0.000060
```

**Analysis**:
- **3-small**: Best cost-effectiveness, good accuracy
- **3-large**: Highest accuracy, but 6.5x more expensive
- **ada-002**: Lower accuracy, higher cost than 3-small
- Recommendation: **text-embedding-3-small** for most use cases

## Troubleshooting

### Redis Connection Errors

```bash
# Ensure Redis is running
docker compose up redis

# Check connection
redis-cli ping
```

### API Connection Errors

```bash
# Ensure API is running
docker compose up

# Check API health
curl http://localhost:3000/api/stats
```

### Import Errors

```bash
# Install missing dependencies
pip install redis requests matplotlib seaborn pandas
```

### All Metrics Constant

If all metrics are constant across thresholds/models:
1. Check that cache is being cleared between tests
2. Verify Redis connection is working
3. Check that queries are unique (no duplicates)
4. Review test logs for errors

## Contributing

When adding new tests or metrics:

1. Follow the existing test structure
2. Document expected behavior
3. Include error handling
4. Add to visualization script if needed
5. Update this README

## References

- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings)
- [OpenAI Pricing](https://openai.com/pricing)
- [MTEB Benchmark](https://huggingface.co/spaces/mteb/leaderboard)

## License

Part of the Boardy Semantic Cache Service project.
