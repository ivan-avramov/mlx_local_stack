# Geopolitics
Act as a United Nations lead researcher preparing a daily global situation briefing.
Today's date is {{CURRENT_DATE}}.

Search for today's most significant news with genuine global balance. Run separate
searches for each of these regions: North America, Latin America, Europe,
Russia/Central Asia, Middle East, Africa, South Asia (India/Pakistan/Bangladesh),
East Asia (China/Japan/Korea), and Southeast Asia.

For each region, identify the 1-2 most significant stories by scale of human impact,
geopolitical consequence, or economic effect — even if under-reported in Western
English-language media.

Format each story as:
**[Region]**
- Headline: summarized headline for the story
- Background: 1-2 sentence summary
- Key points: 2-3 sentence summary
- See More:  include the links for the citations

Where possible, prioritize non-Western sources: Al Jazeera, SCMP, The Hindu,
AllAfrica, Reuters World over CNN/BBC/NYT.

At the end, add a section: **"Under the Radar"** — flag 2-3 stories that appear
globally significant but are receiving little Western media coverage, and briefly
explain why they may matter.

# Tech
Act as a senior technology policy analyst preparing a daily global tech briefing.
Today's date is [DATE].

Search for today's most significant technology news with genuine global balance.
Run separate searches for each of these regions: North America, Latin America,
Europe, Russia/Central Asia, Middle East, Africa, South Asia, East Asia, and
Southeast Asia.

For each region, identify the 1-2 most significant stories by scale of societal
impact, regulatory consequence, or technological advancement — prioritizing stories
about AI, semiconductors, cybersecurity, space, and digital policy, even if
under-reported in Western media.

Format each story as:
**[Region]**
- Headline: summarized headline
- Background: 1-2 sentence context
- Key Points: 2-3 sentence summary
- See More: citation links

Where possible, prioritize sources: SCMP Tech, Nikkei Asia, Rest of World,
MIT Technology Review, The Register over TechCrunch/Wired/Verge.

At the end, add a section: **"Under the Radar"** — flag 2-3 tech developments
that are globally significant but receiving little Western coverage, noting why
they matter (e.g. China semiconductor moves, African fintech, Indian AI policy).

# Finance
Act as a senior global markets analyst preparing a daily financial situation briefing.
Today's date is [DATE].

Search for today's most significant financial and economic news with genuine global
balance. Run separate searches for each of these regions: North America, Latin
America, Europe, Russia/Central Asia, Middle East, Africa, South Asia, East Asia,
and Southeast Asia.

For each region, identify the 1-2 most significant stories by scale of market
impact, macroeconomic consequence, or policy significance — covering central bank
decisions, currency movements, trade, commodities, sovereign debt, and major
corporate developments, even if under-reported in Western financial media.

Format each story as:
**[Region]**
- Headline: summarized headline
- Background: 1-2 sentence context
- Key Points: 2-3 sentence summary
- See More: citation links

Where possible, prioritize sources: Reuters Markets, Nikkei Asia, Financial Times,
Bloomberg (non-paywalled), Caixin (China), Business Standard (India),
African Business over WSJ/CNBC.

At the end, add a section: **"Under the Radar"** — flag 2-3 financial developments
that are globally significant but receiving little Western coverage, noting potential
contagion risk or strategic importance (e.g. EM currency stress, commodity shocks,
de-dollarization moves).

# Science
Act as a senior science correspondent for an international research council preparing
a daily global science briefing.
Today's date is [DATE].

Search for today's most significant science news with genuine global balance.
Run separate searches for each of these regions: North America, Latin America,
Europe, Russia/Central Asia, Middle East, Africa, South Asia, East Asia, and
Southeast Asia.

For each region, identify the 1-2 most significant stories by scientific
advancement, research funding significance, or real-world application potential —
covering physics, biology, climate science, space, materials science, and
emerging fields, even if under-reported in Western science media.

Format each story as:
**[Region]**
- Headline: summarized headline
- Background: 1-2 sentence context
- Key Points: 2-3 sentence summary
- See More: citation links

Where possible, prioritize sources: Nature News, Science, New Scientist,
Xinhua Science, The Wire Science (India), SciDev.Net over popular press.

At the end, add a section: **"Under the Radar"** — flag 2-3 scientific developments
that are globally significant but receiving little mainstream coverage, noting
their potential long-term importance.

# Health
Act as a senior WHO epidemiologist preparing a daily global health situation briefing.
Today's date is [DATE].

Search for today's most significant health and medical news with genuine global
balance. Run separate searches for each of these regions: North America, Latin
America, Europe, Russia/Central Asia, Middle East, Africa, South Asia, East Asia,
and Southeast Asia.

For each region, identify the 1-2 most significant stories by scale of population
impact, disease burden, health policy consequence, or medical advancement —
covering outbreaks, epidemics, drug approvals, health system developments, and
public health crises, even if under-reported in Western health media.

Format each story as:
**[Region]**
- Headline: summarized headline
- Background: 1-2 sentence context
- Key Points: 2-3 sentence summary
- See More: citation links

Where possible, prioritize sources: WHO Situation Reports, The Lancet, BMJ,
Devex Health, Health Policy Watch, ReliefWeb over general news outlets.

At the end, add a section: **"Under the Radar"** — flag 2-3 health developments
that are globally significant but receiving little Western coverage — particularly
outbreaks or health system collapses in low-income regions that may have
cross-border implications.






# example scenarios
To help you visualize how these features work together, here are four scenarios that transform Open WebUI from a chat window into a professional AI operating system.

### Scenario 1: The Automated Newsroom (Prompts & Tools)
**The Goal:** You need to analyze the daily impact of tech news on specific stock sectors.

* **The Setup:** In your **Workspace > Prompts**, you create a prompt named `news-analyst`. The content includes: *"You are a senior financial analyst. Search for the latest news on [Topic], summarize the top 3 trends, and explain the impact on the S&P 500."*
* **The Workflow:** You don't have to type that every time. In any chat, you just type `/news-analyst` and then "Semiconductors."
* **Enhancement:** You attach a **Web Search Tool** to this prompt. Now, every time you use `/news-analyst`, the model automatically browses the live web before answering.

### Scenario 2: The Virtual Engineering Firm (Models & Channels)
**The Goal:** You want to design a new software system with specialized critiques from an Architect, a Tester, and a Technical Writer.

* **The Setup (Models):** In **Workspace > Models**, you create three "Modelfiles":
    * **Architect Agent:** Base model + System Prompt: *"Focus on system scalability, CAP theorem, and modularity."*
    * **Test Agent:** Base model + System Prompt: *"Focus on edge cases, unit test coverage, and security vulnerabilities."*
    * **TechnicalWriter:** Base model + System Prompt: *"Translate technical jargon into clear documentation."*
* **The Workflow (Channels):** You create a **Channel** called `#project-alpha`. You invite your human team members and add these three models to the channel.
* **The Interaction:** 1.  You type: *"@Architect, how should we structure our database for a high-traffic app?"*
    2.  Once the Architect replies, you type: *"@Test, what are the primary risks in the Architect’s proposed plan?"*
    3.  Finally, you type: *"@TechnicalWriter, summarize this discussion into a project brief."*



### Scenario 3: The Deep-Dive Researcher (Knowledge & Notes)
**The Goal:** You are studying **Apache Iceberg** and want to build a "second brain" on the topic that persists across weeks of study.

* **The Setup (Knowledge):** In **Workspace > Knowledge**, you create a collection called `Data-Lakes`. You upload the Apache Iceberg whitepapers and documentation PDFs.
* **The Workflow (Notes):** As you chat with the AI about the storage layer, you find a breakthrough realization. You click "Create Note" from the chat.
    * You name the note `Iceberg Conclusions`.
    * In future chats, you **tag this note** (using the `#` symbol). The AI now has the exact context of your previous conclusions without you needing to repeat yourself.
* **Summarization:** After a 50-message exploration of "Snapshot Isolation," you ask the AI: *"Using your 'write_note' tool, summarize our conclusions about Snapshot Isolation into my 'Iceberg Conclusions' note."* The AI updates your document live.



### Scenario 4: The Executive Assistant (Memory & Folders)
**The Goal:** You want the AI to remember that you prefer Python over Java and that you work in a specific cloud environment (e.g., AWS), so you don't have to tell it every time.

* **The Setup (Memory):** Open WebUI has a **Memory** feature (often found in User Settings). You can explicitly tell it: *"Remember that all my architecture work happens on AWS and I prefer Terraform for Infrastructure as Code."*
* **The Setup (Folders):** You create a **Folder** called `Active Projects`. Inside, you create a subfolder for `AWS-Migration`.
* **The Workflow:** When you start a chat in the `AWS-Migration` folder, the AI already knows you use Terraform (from Memory) and has access to your migration checklists (from the Folder-level Knowledge base). If you ask, *"Remind me what we decided about the load balancer last Tuesday,"* the AI can scan your previous chat history or notes to pull that conclusion.

---

### Other Useful Scenarios

1.  **Legal/Compliance Review:** Create a **Knowledge Base** of your company’s legal contracts. Use a **Model** configured as a "Compliance Officer" to check new drafts against the stored "Knowledge" to find contradictions.
2.  **Language Learning Lab:** Create a **Channel** for "Spanish Practice." Use a **Model** configured as a "Tutor" that only responds in Spanish but provides English translations in **Notes** side-by-side.
3.  **Content Factory:** Create a **Note** that serves as your "Brand Voice Guide." Tag that note whenever you ask the AI to write a blog post or tweet, ensuring the output always matches your style without re-pasting the guide.
4.  **Code Maintenance:** Mount your local code directory (as a **Live Sync**). Create a **Model** named "Refactor Bot." You can then ask: *"@RefactorBot, look at my `auth.py` file and update it to use the new library version we discussed in our 'Security Notes'."*

By combining these, you move away from "asking questions" and toward "managing a workforce." Does one of these scenarios align most closely with what you're trying to build first?







# Cloud verifier
Absolutely. This "hybrid" setup—mixing local hardware with high-end cloud intelligence—is one of the most popular ways to use Open WebUI.

Since it is **2026**, the Gemini 3 ecosystem is now the standard. Here is exactly how to build your "Verification Channel" with a local MLX backend and external Gemini models.

---

### 1. The Local Setup (MLX Backend)
On a Mac, you aren't limited to just Ollama. Since you're using **MLX**, you are likely running models via the `mlx-lm` library.
* **How to connect:** You need to run an OpenAI-compatible server for your local model. In your terminal, run:
  ```bash
  python -m mlx_lm.server --model /path/to/your/local-model
  ```
  This will host your model at `http://localhost:8080/v1`.
* **In Open WebUI:** Go to **Admin Settings > Connections > OpenAI** and click the **+ (Plus)** button to add a new connection.
  * **Base URL:** `http://localhost:8080/v1`
  * **API Key:** `none` (unless you set one in the server).

### 2. The Cloud Setup (Gemini 3)
You can connect Gemini directly through the built-in **Gemini Connection** or the **OpenAI-Compatible** bridge.

#### Do you need a paid plan?
* **Free Tier:** In Google AI Studio, **Gemini 3 Flash** and **Gemini 3.1 Flash-Lite** are generally free to use (with rate limits).
* **Pro Tier:** **Gemini 3.1 Pro** (the "thinking" model) usually requires you to have a **payment method on file**, even if you stay within the free monthly quota. If you want the "highest intelligence" for verification, you'll likely need to attach a credit card to your Google Cloud project.

#### Model Selection (Fast, Thinking, Pro)
You do **not** need a separate connection for each. You define them in the **Model IDs** field of your Gemini connection.
* **Fast:** `gemini-3-flash-preview`
* **Intelligent/Thinking:** `gemini-3.1-pro-preview`
* **Ultra-Fast:** `gemini-3.1-flash-lite-preview`

---

### 3. The "Verification" Workflow in Channels
Once both are connected, they will appear as separate choices in your model dropdown. Here is how to use them in a **Channel**:

1.  **Create a Channel:** Call it `#dev-architecture` or `#code-verify`.
2.  **The Prompting Sequence:** * **User:** `@local-llama-3 Please draft a Python script to handle these Apache Iceberg snapshots.`
    * *(Local model generates code)*
    * **User:** `@gemini-3.1-pro Please review the code provided above by the local model. Check specifically for logical errors in the snapshot expiration logic.`
3.  **Cross-Model Awareness:** Because both models are in the same **Channel**, Gemini can "read" the message sent by your local model as part of the shared chat history.

---

### Summary Checklist

| Feature | Configuration Detail |
| :--- | :--- |
| **Local Connection** | Point Open WebUI to your `mlx-lm` server (`localhost:8080/v1`). |
| **Gemini Connection** | Use `https://generativelanguage.googleapis.com/v1beta/openai/` as the Base URL. |
| **Gemini API Key** | Get this for free from [Google AI Studio](https://aistudio.google.com). |
| **Model Selection** | Add model names like `gemini-3.1-pro-preview` to the "Model IDs" allowlist. |
| **@Mentioning** | Just type `@` in a channel to pick between your Mac and Google's cloud. |

> **Pro Tip:** If you want Gemini to be *extremely* critical, create a **Model** in your **Workspace** based on Gemini 3.1 Pro and name it "System Validator." Give it a system prompt: *"Your only job is to find flaws in the previous AI's logic."* Now you can just type `@SystemValidator` to trigger a specialized audit.

Are you planning to run a specific local model like Llama 3 or Mistral on your Mac for the primary heavy lifting?



# me

Approach every topic as a senior systems architect would. Cover:
1. Internal architecture and design decisions — not just API/surface behavior
2. The tradeoff space the designers optimized for
3. Operational behavior at scale and at edge cases
4. Comparison to alternatives by deployment model fit, not abstract ranking
5. Failure modes and degradation behavior
6. Practical constraints: cost, complexity, maintainability

Assume strong technical background. Skip basics unless specifically asked.
Take positions — "it depends" is only acceptable with explicit criteria attached.
Push back if the question contains a flawed assumption.
Flag second-order effects and long-term implications proactively.


# Benchmark suggestions
Given your background, the most informative tests would be ones you can actually evaluate correctly yourself rather than relying on model self-assessment. A few categories:

**Distributed systems / your domain**

Design a strongly consistent distributed transaction protocol with a specific constraint set — something like "single-leader with follower reads, sub-millisecond p99 latency budget, network partition handling." You'll immediately know if the reasoning is sound or if it's plausibly-worded nonsense. This is better than generic benchmarks precisely because you can't be fooled.

**Real agentic coding task**

Give it a non-trivial but bounded real task from your mlx-vlm work — something like implementing the `DeltaNetCache` checkpoint/restore interface we discussed. You get to evaluate: does it understand the architecture constraints without being told twice, does it produce correct code first pass, does it handle the heterogeneous dispatch correctly. Real signal, not synthetic.

**Math with verifiable answer**

A multi-step calculus or linear algebra problem where you can check the answer and the intermediate steps independently — not competition math format which favors Qwen's training distribution, but applied problems like deriving a recurrence relation or solving a differential equation that arises naturally in something you care about.

**Tool use under pressure**

A multi-turn agentic task that requires correct tool call sequencing, state tracking across turns, and recovery from a deliberate mid-task contradiction you introduce. Tests whether the model actually tracks state or just pattern-matches on the most recent context.

**The meta-test worth doing first**

Before any of the above — ask both models to explain the DeltaNet rewind problem and propose a solution, without giving them any of our conversation context. Compare against what we worked out here. You already know the correct answer, the failure modes, and the subtle points. It's the perfect blind evaluation where you're the ground truth.


# Benchmarks for quantized variants
For comparing **different models/sizes** you want tasks where capability differences dominate noise — the gap needs to be large enough to survive prompt variation:

- **Multi-hop distributed systems reasoning**: "Design a log replication protocol that maintains linearizability under concurrent writes with a follower that has 200ms clock skew. Identify all failure modes." A weaker model will miss non-obvious failure modes or propose solutions with subtle consistency violations you'll recognize immediately.
- **Novel proof construction**: Give a math statement that requires combining two non-obvious techniques — e.g. proving convergence of a recurrence using both generating functions and a fixed-point argument. A smaller model collapses to one technique.
- **Long agentic task with accumulated state**: 10+ turn task where early decisions constrain later ones. Smaller models lose the thread.

---

For comparing **bit depth variants (4bit vs 6bit uniform)**  you want tasks sensitive to precision degradation, which shows up as:

- **Numerical stability**: Ask it to symbolically derive a Taylor expansion to 6th order, then evaluate at a boundary value. Quantization artifacts show up as dropped terms or coefficient errors.
- **Subtle instruction following**: A prompt with 8-10 specific constraints simultaneously. Lower precision models start dropping constraints around constraint 6-7.
- **Exact code reproduction pattern**: Ask it to implement a specific well-known algorithm (e.g. Raft leader election) and check for subtle correctness issues — wrong comparison operators, off-by-one in term tracking, etc.

---

For comparing **UD vs uniform at the same bit depth** the signal is much subtler — you're looking for quality differences in the layers UD specifically protects:

- **First-token coherence on complex prompts**: UD's layer upscaling most benefits early layer representations. Give a prompt with ambiguous referents and subtle context dependencies — "Given the protocol above, if node A fails after step 3 but before step 4's acknowledgment, and node B had already applied the tentative write..." — and check if the model correctly resolves which "step 3" and "write" are being referenced.
- **Tool call JSON correctness on nested schemas**: UD specifically improves tool calling per Unsloth's notes. Give a deeply nested tool schema with 4-5 levels and optional fields, call it multiple times in a session. Count malformed outputs. Uniform quantization drops bits on the output projection layers that matter most for structured generation.
- **Repetition under long context**: At 150K+ tokens, uniform quantization models show repetition or topic drift before UD equivalents. Feed a long document and ask for synthesis at the end — uniform models start looping or lose early document details.

---

For comparing **UD-4bit vs uniform-6bit** specifically (your actual decision):

These three are the highest-signal tests for that exact comparison:

1. **Nested tool call schema** as above — this is where UD-4bit is most likely to beat uniform-6bit concretely and measurably
2. **Code with subtle bug injection**: Write a correct implementation, introduce a single subtle semantic bug (wrong memory ordering assumption, incorrect epoch comparison), ask the model to review and find issues. UD-4bit's better preservation of reasoning layers should catch it more reliably
3. **256K context coherence test**: Only possible after you've switched — load a long technical document or codebase, ask questions that require connecting information from the beginning and end simultaneously. The model that maintains coherence longer wins, and this directly validates whether the memory headroom gain was worth the bit reduction

---

**Practical advice**: run each test 3 times per model variant with temperature > 0 and look for consistency, not just peak performance. A model that gets it right once but varies wildly is less useful than one that's consistently slightly worse. Given Gemma4's known consistency advantage, this matters especially for that comparison.
