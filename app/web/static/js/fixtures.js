/**
 * Mock Data Fixtures for UI validation & offline development mode (?mock=1)
 */

export const mockArticles = [
  {
    id: "art_mock_01",
    source_id: "src_hn",
    source_name: "Hacker News",
    url: "https://news.ycombinator.com/item?id=3912345",
    title: "DeepSeek-V3 Architecture: Multi-head Latent Attention and DeepSeekMoE Explained",
    summary: "A technical deep-dive into the architectural innovations behind DeepSeek-V3, focusing on how MLA drastically cuts KV-cache memory and MoE load balancing.",
    category: "AI_LLM",
    published_at_utc: new Date(Date.now() - 25 * 60 * 1000).toISOString(),
    score_cached: 48.5,
    cluster_id: "cls_01",
    cluster_size: 4,
    is_read: 0,
    is_bookmarked: 1,
    tags: ["LLM", "DeepSeek", "Attention", "MoE"]
  },
  {
    id: "art_mock_02",
    source_id: "src_towardsds",
    source_name: "Towards Data Science",
    url: "https://towardsdatascience.com/production-rag-evaluation-framework-2026",
    title: "Evaluating RAG Pipelines in Production: Metrics That Actually Correlate with User Trust",
    summary: "Faithfulness, Answer Relevance, and Context Recall are standard, but here is how top engineering teams quantify hallucination severity and retrieval latency.",
    category: "DATA_SCIENCE_ML",
    published_at_utc: new Date(Date.now() - 110 * 60 * 1000).toISOString(),
    score_cached: 42.1,
    cluster_id: null,
    cluster_size: 1,
    is_read: 0,
    is_bookmarked: 0,
    tags: ["RAG", "Data Science", "Evaluation", "MLOps"]
  },
  {
    id: "art_mock_03",
    source_id: "src_techcrunch",
    source_name: "TechCrunch",
    url: "https://techcrunch.com/2026/09/20/open-source-foundation-models-benchmark",
    title: "Open Weights Surge: Benchmark Shows Small Models Outperforming GPT-4 on Code Tasks",
    summary: "New synthetic fine-tuning datasets combined with test-time compute reasoning allow 7B and 14B models to reach 86% on HumanEval benchmarks.",
    category: "AI_LLM",
    published_at_utc: new Date(Date.now() - 260 * 60 * 1000).toISOString(),
    score_cached: 39.8,
    cluster_id: "cls_01",
    cluster_size: 4,
    is_read: 1,
    is_bookmarked: 0,
    tags: ["Open Source", "Benchmarks", "Coding"]
  },
  {
    id: "art_mock_04",
    source_id: "src_arstechnica",
    source_name: "Ars Technica",
    url: "https://arstechnica.com/gadgets/2026/09/next-gen-ai-accelerators-break-memory-wall",
    title: "Next-Gen AI Hardware Accelerators Target the Silicon Memory Wall",
    summary: "As memory bandwidth bottlenecks generative model inference, chipmakers are turning to optical interconnects and 3D stacked HBM4 dies.",
    category: "TECH_GENERAL",
    published_at_utc: new Date(Date.now() - 520 * 60 * 1000).toISOString(),
    score_cached: 33.2,
    cluster_id: null,
    cluster_size: 1,
    is_read: 0,
    is_bookmarked: 0,
    tags: ["Hardware", "Semiconductors", "HBM4"]
  }
];

export const mockPapers = [
  {
    id: "paper_mock_01",
    source_id: "src_arxiv",
    source_name: "arXiv cs.AI",
    url: "https://arxiv.org/abs/2609.09876",
    title: "Reasoning via Self-Play Verification: Provable Bounds on Exploration Efficiency",
    summary: "We present a mathematical framework for verification-guided search during reasoning model pre-training and inference. By decoupling candidate proposal from formal semantic verification, our method achieves 2.4x higher sample efficiency on complex Olympiad mathematics.",
    category: "AI_RESEARCH",
    published_at_utc: new Date(Date.now() - 180 * 60 * 1000).toISOString(),
    is_read: 0,
    is_bookmarked: 1,
    tags: ["cs.AI", "cs.LG", "Reasoning", "Verification"]
  },
  {
    id: "paper_mock_02",
    source_id: "src_arxiv",
    source_name: "arXiv cs.CL",
    url: "https://arxiv.org/abs/2609.09543",
    title: "Scalable KV-Cache Compression via Dynamic Spectral Quantization",
    summary: "Transformer context scaling is fundamentally constrained by key-value cache memory footprints. We introduce SpectralKV, a 2-bit quantization technique with dynamic outlier retention that enables 1M token contexts on a single 80GB GPU.",
    category: "AI_RESEARCH",
    published_at_utc: new Date(Date.now() - 360 * 60 * 1000).toISOString(),
    is_read: 0,
    is_bookmarked: 0,
    tags: ["cs.CL", "Quantization", "Long Context"]
  }
];

export const mockDigest = {
  digest_date: new Date().toISOString().split('T')[0],
  content_md: `## Executive Summary: Key AI & Data Science Developments

Today's intelligence analysis highlights rapid progress in **reasoning model verification**, **KV-cache quantization breakthroughs**, and the expanding viability of small open-weights models for automated software engineering.

---

### 1. Breakthroughs in Reasoning & Architectural Efficiency
* **Verification-Driven Search**: Recent research shows test-time search guided by formal code verifiers outperforms pure probabilistic sampling by [2.4x on math tasks](https://arxiv.org/abs/2609.09876).
* **Multi-head Latent Attention (MLA)**: Broad adoption of latent attention compression allows production inference engines to sustain massive concurrency without exponential VRAM growth.

### 2. Applied Data Science & Production Systems
* **RAG Evaluation Maturity**: Teams are shifting from generic perplexity scores to granular semantic correctness and hallucination severity indices.
* **Hardware Evolution**: Next-gen memory architectures (HBM4 and optical interconnects) are alleviating inference memory bandwidth bottlenecks.

### 3. Industry & Strategic Landscape
* **Edge Reasoning**: 7B and 14B models with synthetic step-by-step reasoning datasets are approaching parity with proprietary frontier models on specific programming benchmarks.
`
};

export const mockSources = [
  {
    id: "src_hn",
    name: "Hacker News",
    kind: "rss",
    feed_url: "https://news.ycombinator.com/rss",
    category_hint: "TECH_GENERAL",
    authority: 1.0,
    enabled: 1,
    last_success_at: new Date(Date.now() - 12 * 60 * 1000).toISOString(),
    consecutive_failures: 0
  },
  {
    id: "src_arxiv",
    name: "arXiv cs.AI / cs.CL",
    kind: "arxiv",
    feed_url: "http://export.arxiv.org/rss/cs.AI",
    category_hint: "AI_RESEARCH",
    authority: 0.95,
    enabled: 1,
    last_success_at: new Date(Date.now() - 15 * 60 * 1000).toISOString(),
    consecutive_failures: 0
  },
  {
    id: "src_towardsds",
    name: "Towards Data Science",
    kind: "rss",
    feed_url: "https://towardsdatascience.com/feed",
    category_hint: "DATA_SCIENCE_ML",
    authority: 0.85,
    enabled: 1,
    last_success_at: new Date(Date.now() - 25 * 60 * 1000).toISOString(),
    consecutive_failures: 0
  },
  {
    id: "src_verge",
    name: "The Verge",
    kind: "rss",
    feed_url: "https://www.theverge.com/rss/index.xml",
    category_hint: "TECH_GENERAL",
    authority: 1.0,
    enabled: 1,
    last_success_at: new Date(Date.now() - 36 * 3600 * 1000).toISOString(),
    consecutive_failures: 0
  }
];

export const mockChatResponse = {
  answer: "Based on today's intelligence feed, the most notable open-weights LLM development is the emergence of smaller 7B-14B reasoning models achieving 86% on HumanEval [1]. Additionally, DeepSeek-V3's Multi-head Latent Attention architecture has established a new standard for KV-cache memory efficiency in large-scale deployments [2].",
  model_used: "Gemini 3.5 Flash",
  sources: [
    {
      index: 1,
      title: "Open Weights Surge: Benchmark Shows Small Models Outperforming GPT-4 on Code Tasks",
      url: "https://techcrunch.com/2026/09/20/open-source-foundation-models-benchmark",
      source: "TechCrunch"
    },
    {
      index: 2,
      title: "DeepSeek-V3 Architecture: Multi-head Latent Attention and DeepSeekMoE Explained",
      url: "https://news.ycombinator.com/item?id=3912345",
      source: "Hacker News"
    }
  ]
};
