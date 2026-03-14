import aiosqlite
import os

DB_PATH = os.getenv("DB_PATH", "/data/newsflow.db")

async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            is_admin INTEGER DEFAULT 0,
            tracking_token TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS topics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL,
            icon TEXT DEFAULT '📰',
            feed_urls TEXT DEFAULT '[]',
            search_queries TEXT DEFAULT '[]',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_topics (
            user_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, topic_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        );

        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source TEXT,
            author TEXT,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary TEXT,
            ai_summary TEXT,
            image_url TEXT,
            topic_id INTEGER,
            content TEXT,
            FOREIGN KEY (topic_id) REFERENCES topics(id)
        );

        CREATE TABLE IF NOT EXISTS user_article_interactions (
            user_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            score REAL DEFAULT 0,
            interacted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, article_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (article_id) REFERENCES articles(id)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            PRIMARY KEY (user_id, key),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS digest_schedule (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            enabled INTEGER DEFAULT 0,
            send_times TEXT DEFAULT '["07:00"]',
            timezone TEXT DEFAULT 'UTC',
            last_sent TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS custom_feeds (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            url TEXT NOT NULL,
            name TEXT DEFAULT '',
            topic_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, url),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_articles_topic ON articles(topic_id);
        CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at DESC);
        CREATE INDEX IF NOT EXISTS idx_interactions_user ON user_article_interactions(user_id);

        -- Per-user per-topic affinity scores (computed, cached, updated on interaction)
        CREATE TABLE IF NOT EXISTS user_topic_affinity (
            user_id INTEGER NOT NULL,
            topic_id INTEGER NOT NULL,
            score REAL DEFAULT 0.5,
            interaction_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, topic_id)
        );

        -- Article click-through tracking (separate from button interactions)
        CREATE TABLE IF NOT EXISTS article_clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            clicked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (article_id) REFERENCES articles(id)
        );
        CREATE INDEX IF NOT EXISTS idx_clicks_user ON article_clicks(user_id, clicked_at);
        CREATE INDEX IF NOT EXISTS idx_interactions_article ON user_article_interactions(article_id);

        -- Permanent per-user per-article share tokens
        -- token: 22-char URL-safe base64 (128-bit random) — ~3.4×10³⁸ possible values
        -- Each user gets their own token per article so clicks are always attributable
        CREATE TABLE IF NOT EXISTS share_links (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            click_count INTEGER DEFAULT 0,
            last_clicked TIMESTAMP,
            UNIQUE(user_id, article_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (article_id) REFERENCES articles(id)
        );
        CREATE INDEX IF NOT EXISTS idx_share_links_user ON share_links(user_id);
        CREATE INDEX IF NOT EXISTS idx_share_links_article ON share_links(article_id);

        -- Read later / saved articles (separate from interactions so like+save can coexist)
        CREATE TABLE IF NOT EXISTS saved_articles (
            user_id INTEGER NOT NULL,
            article_id INTEGER NOT NULL,
            saved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, article_id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (article_id) REFERENCES articles(id)
        );
        CREATE INDEX IF NOT EXISTS idx_saved_user ON saved_articles(user_id, saved_at DESC);

        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            used INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX IF NOT EXISTS idx_password_resets_token ON password_resets(token);
        """)
        await db.commit()
        await _seed_default_settings(db)
        await _seed_topics(db)

async def _seed_default_settings(db):
    defaults = [
        ("ollama_url", "http://localhost:11434"),
        ("ollama_model", "llama3.1:8b"),
        ("refresh_interval_minutes", "60"),
        ("newsapi_key", ""),
        ("smtp_host", ""),
        ("smtp_port", "587"),
        ("smtp_user", ""),
        ("smtp_password", ""),
        ("smtp_from", ""),
        ("max_articles_per_topic", "20"),
        ("auto_summarize", "true"),
        ("site_url", ""),
        ("article_retention_days", "30"),
        ("read_later_expiry_days", "30"),
        ("allow_signups", "true"),
    ]
    for key, value in defaults:
        await db.execute(
            "INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, ?)",
            (key, value)
        )
    await db.commit()

async def _seed_topics(db):
    topics = [
        # ── Technology: AI & ML ───────────────────────────────────────────────
        ("Artificial Intelligence", "artificial-intelligence", "Technology: AI & ML", "🤖",
         '["https://rss.arxiv.org/rss/cs.AI","https://openai.com/blog/rss/","https://www.technologyreview.com/feed/","https://huggingface.co/blog/feed.xml"]',
         '["artificial intelligence","machine learning","deep learning","LLM","ChatGPT","Gemini"]'),
        ("Machine Learning", "machine-learning", "Technology: AI & ML", "📊",
         '["https://rss.arxiv.org/rss/cs.LG","https://machinelearningmastery.com/feed/","https://thegradient.pub/rss/"]',
         '["machine learning","neural network","deep learning","PyTorch","TensorFlow","transformer"]'),
        ("Large Language Models", "llms", "Technology: AI & ML", "💬",
         '["https://www.interconnects.ai/feed","https://simonwillison.net/atom/everything/"]',
         '["LLM","large language model","GPT","Llama","Mistral","Anthropic","OpenAI","fine-tuning","RAG"]'),
        ("AI Image & Video", "ai-image-video", "Technology: AI & ML", "🖼️",
         '["https://stability.ai/blog/rss"]',
         '["Stable Diffusion","Midjourney","DALL-E","Sora","AI image generation","text to video","AI art","diffusion model"]'),

        # ── Technology: Security ──────────────────────────────────────────────
        ("Cybersecurity", "cybersecurity", "Technology: Security", "🔐",
         '["https://feeds.feedburner.com/TheHackersNews","https://krebsonsecurity.com/feed/","https://www.schneier.com/feed/atom/","https://isc.sans.edu/rssfeed.xml"]',
         '["cybersecurity","hacking","data breach","ransomware","vulnerability","infosec","zero day","CVE"]'),
        ("Privacy & Surveillance", "privacy-surveillance", "Technology: Security", "👁️",
         '["https://www.eff.org/rss/updates.xml","https://spreadprivacy.com/rss/"]',
         '["privacy","surveillance","data collection","GDPR","facial recognition","tracking","data protection"]'),

        # ── Technology: Dev ───────────────────────────────────────────────────
        ("Software Development", "software-development", "Technology: Dev", "💻",
         '["https://hnrss.org/frontpage","https://dev.to/feed","https://lobste.rs/rss","https://changelog.com/news/feed"]',
         '["programming","software development","coding","open source","developer tools","API","framework","architecture"]'),
        ("Linux & Open Source", "linux-open-source", "Technology: Dev", "🐧",
         '["https://opensource.com/feed","https://lwn.net/headlines/rss","https://www.phoronix.com/rss.php","https://itsfoss.com/feed/"]',
         '["Linux","open source","GitHub","free software","kernel","Ubuntu","Debian","Arch","BSD"]'),
        ("Programming Languages", "programming-languages", "Technology: Dev", "⌨️",
         '["https://blog.rust-lang.org/feed.xml","https://go.dev/blog/feed.atom"]',
         '["Python","Rust","Go","TypeScript","JavaScript","programming language","compiler","interpreter"]'),
        ("DevOps & Infrastructure", "devops", "Technology: Dev", "⚙️",
         '["https://devops.com/feed/","https://thenewstack.io/feed/"]',
         '["DevOps","Kubernetes","Docker","CI/CD","Terraform","cloud native","SRE","infrastructure as code"]'),

        # ── Technology: Hardware ──────────────────────────────────────────────
        ("Gadgets & Hardware", "gadgets-hardware", "Technology: Hardware", "📱",
         '["https://www.theverge.com/rss/index.xml","https://www.tomshardware.com/feeds/all","https://arstechnica.com/gadgets/feed/"]',
         '["gadgets","hardware","smartphones","electronics","review","benchmark","wearables","headphones"]'),
        ("PC & Gaming Hardware", "pc-gaming-hardware", "Technology: Hardware", "🖥️",
         '["https://www.tomshardware.com/feeds/all","https://www.techpowerup.com/rss/news.xml"]',
         '["PC hardware","GPU","CPU","AMD","NVIDIA","Intel","RAM","motherboard","cooling","overclock","build"]'),
        ("Semiconductors & Chips", "semiconductors", "Technology: Hardware", "🔬",
         '["https://semianalysis.com/feed/","https://spectrum.ieee.org/feeds/topic/semiconductors.rss"]',
         '["semiconductor","chips","TSMC","Intel foundry","silicon","fabrication","RISC-V","ARM","node"]'),

        # ── Technology: Science ───────────────────────────────────────────────
        ("Space & Astronomy", "space-astronomy", "Technology: Science", "🚀",
         '["https://www.nasa.gov/rss/dyn/breaking_news.rss","https://www.space.com/feeds/all","https://spacenews.com/feed/","https://www.nasaspaceflight.com/feed/"]',
         '["space","NASA","SpaceX","rocket","satellite","Mars","telescope","launch","astronaut","Starship"]'),
        ("Quantum Computing", "quantum-computing", "Technology: Science", "⚛️",
         '["https://quantumcomputingreport.com/feed/","https://spectrum.ieee.org/feeds/topic/quantum-computing.rss"]',
         '["quantum computing","qubit","quantum supremacy","IBM quantum","Google quantum","error correction"]'),
        ("Robotics & Automation", "robotics-automation", "Technology: Science", "🦾",
         '["https://spectrum.ieee.org/feeds/topic/robotics.rss","https://www.therobotreport.com/feed/"]',
         '["robotics","robot","automation","Boston Dynamics","humanoid robot","drone","industrial robot","Figure"]'),

        # ── Technology: Transport ─────────────────────────────────────────────
        ("Electric Vehicles", "electric-vehicles", "Technology: Transport", "⚡",
         '["https://electrek.co/feed/","https://insideevs.com/feed/","https://cleantechnica.com/feed/"]',
         '["electric vehicles","Tesla","EV","battery","charging","Rivian","Lucid","BYD","range","charging network"]'),
        ("Autonomous Vehicles", "autonomous-vehicles", "Technology: Transport", "🚗",
         '["https://techcrunch.com/tag/self-driving-cars/feed/"]',
         '["self-driving","autonomous vehicle","Waymo","Tesla Autopilot","LIDAR","robotaxi","AV"]'),

        # ── Technology: Business ──────────────────────────────────────────────
        ("Cloud & SaaS", "cloud-saas", "Technology: Business", "☁️",
         '["https://aws.amazon.com/blogs/aws/feed/","https://cloudblogs.microsoft.com/feed/","https://cloud.google.com/blog/rss/"]',
         '["cloud computing","AWS","Azure","Google Cloud","SaaS","Kubernetes","serverless","microservices"]'),
        ("Big Tech", "big-tech", "Technology: Business", "🏢",
         '["https://arstechnica.com/tech-policy/feed/","https://www.theverge.com/rss/index.xml"]',
         '["Apple","Google","Microsoft","Meta","Amazon","Big Tech","antitrust","regulation","earnings","FAANG"]'),
        ("Tech Policy & Regulation", "tech-policy", "Technology: Business", "⚖️",
         '["https://arstechnica.com/tech-policy/feed/","https://www.eff.org/rss/updates.xml","https://techpolicy.press/feed/"]',
         '["tech regulation","antitrust","AI regulation","Section 230","data privacy law","FTC","EU tech"]'),

        # ── Technology: Emerging ──────────────────────────────────────────────
        ("AR & VR", "ar-vr", "Technology: Emerging", "🥽",
         '["https://www.roadtovr.com/feed/","https://uploadvr.com/feed/"]',
         '["augmented reality","virtual reality","AR","VR","Meta Quest","Apple Vision Pro","spatial computing","XR"]'),
        ("Blockchain & Web3", "blockchain-web3", "Technology: Emerging", "🔗",
         '["https://decrypt.co/feed","https://thedefiant.io/feed"]',
         '["blockchain","Web3","NFT","smart contracts","Ethereum","DeFi","crypto","DAO"]'),
        ("Biotech", "biotech", "Technology: Emerging", "🧫",
         '["https://www.fiercebiotech.com/rss/","https://www.statnews.com/feed/"]',
         '["biotech","gene therapy","CRISPR","mRNA","synthetic biology","longevity","bioinformatics","drug discovery"]'),

        # ── Science ───────────────────────────────────────────────────────────
        ("Climate & Environment", "climate-environment", "Science", "🌍",
         '["https://www.carbonbrief.org/feed","https://insideclimatenews.org/feed"]',
         '["climate change","global warming","environment","renewable energy","emissions","IPCC","net zero"]'),
        ("Biology & Medicine", "biology-medicine", "Science", "🧬",
         '["https://feeds.nature.com/nature/rss/current","https://www.sciencedaily.com/rss/health_medicine.xml"]',
         '["biology","medicine","genetics","CRISPR","vaccine","stem cell","genomics"]'),
        ("Physics", "physics", "Science", "⚗️",
         '["https://physics.aps.org/rss/recentarticles.xml","https://rss.arxiv.org/rss/physics"]',
         '["physics","particle physics","quantum","CERN","dark matter","gravitational waves","fusion"]'),
        ("Neuroscience", "neuroscience", "Science", "🧠",
         '["https://www.sciencedaily.com/rss/mind_brain.xml"]',
         '["neuroscience","brain","neurology","consciousness","cognition","Alzheimer","fMRI"]'),
        ("Mathematics", "mathematics", "Science", "📐",
         '["https://rss.arxiv.org/rss/math"]',
         '["mathematics","statistics","proof","algorithm","number theory","topology","combinatorics"]'),
        ("Archaeology", "archaeology", "Science", "🏺",
         '["https://www.livescience.com/feeds/all"]',
         '["archaeology","ancient","excavation","fossil","discovery","prehistoric","Roman","Egypt"]'),

        # ── Finance ───────────────────────────────────────────────────────────
        ("Stock Market", "stock-market", "Finance", "📈",
         '["https://feeds.marketwatch.com/marketwatch/topstories/","https://feeds.finance.yahoo.com/rss/2.0/headline"]',
         '["stock market","S&P 500","NYSE","NASDAQ","investing","earnings","Fed","interest rates"]'),
        ("Cryptocurrency", "cryptocurrency", "Finance", "₿",
         '["https://cointelegraph.com/rss","https://coindesk.com/arc/outboundfeeds/rss/","https://decrypt.co/feed"]',
         '["cryptocurrency","Bitcoin","Ethereum","blockchain","DeFi","altcoin","crypto market","stablecoin"]'),
        ("Startups & VC", "startups-vc", "Finance", "💡",
         '["https://techcrunch.com/feed/","https://news.crunchbase.com/feed/"]',
         '["startup","venture capital","funding","Series A","unicorn","YCombinator","IPO","angel investor"]'),
        ("Real Estate", "real-estate", "Finance", "🏠",
         '["https://www.inman.com/feed/"]',
         '["real estate","housing market","mortgage","property","interest rates","housing prices"]'),
        ("Personal Finance", "personal-finance", "Finance", "💰",
         '["https://feeds.feedburner.com/MrMoneyMustache","https://www.getrichslowly.org/feed/"]',
         '["personal finance","savings","retirement","budgeting","investing","FIRE","financial independence"]'),
        ("Global Economy", "global-economy", "Finance", "🌐",
         '["https://feeds.bbci.co.uk/news/business/rss.xml","https://feeds.feedburner.com/ft-economics"]',
         '["economy","GDP","inflation","Federal Reserve","interest rates","recession","trade war","tariffs"]'),

        # ── World News ────────────────────────────────────────────────────────
        ("International News", "international-news", "World News", "🌏",
         '["https://feeds.bbci.co.uk/news/world/rss.xml","https://feeds.npr.org/1004/rss.xml"]',
         '["international","world news","geopolitics","United Nations","conflict","diplomacy","sanctions"]'),
        ("US Politics", "us-politics", "World News", "🏛️",
         '["https://feeds.npr.org/1014/rss.xml","https://rss.nytimes.com/services/xml/rss/nyt/Politics.xml"]',
         '["US politics","Congress","Senate","White House","election","Washington","Trump","Biden"]'),
        ("Europe", "europe", "World News", "🇪🇺",
         '["https://feeds.bbci.co.uk/news/world/europe/rss.xml","https://www.euronews.com/rss"]',
         '["Europe","European Union","NATO","Germany","France","Brexit","EU policy"]'),
        ("Asia Pacific", "asia-pacific", "World News", "🌏",
         '["https://feeds.bbci.co.uk/news/world/asia/rss.xml","https://www.scmp.com/rss/91/feed"]',
         '["Asia","China","Japan","India","South Korea","Taiwan","ASEAN","Indo-Pacific"]'),
        ("Middle East", "middle-east", "World News", "🕌",
         '["https://feeds.bbci.co.uk/news/world/middle_east/rss.xml"]',
         '["Middle East","Israel","Iran","Saudi Arabia","conflict","Gulf","OPEC","Gaza"]'),
        ("Australia & Pacific", "australia-pacific", "World News", "🦘",
         '["https://www.abc.net.au/news/feed/2942460/rss.xml","https://www.rnz.co.nz/rss/news.xml","https://feeds.bbci.co.uk/news/world/australia/rss.xml"]',
         '["Australia","New Zealand","Pacific","AUKUS","Pacific Islands","Aboriginal","Maori"]'),
        ("Canada", "canada", "World News", "🍁",
         '["https://www.cbc.ca/cmlink/rss-topstories","https://globalnews.ca/feed/"]',
         '["Canada","Ottawa","Toronto","Vancouver","Canadian politics","Alberta","Quebec"]'),
        ("UK & Ireland", "uk-ireland", "World News", "🇬🇧",
         '["https://feeds.bbci.co.uk/news/uk/rss.xml","https://www.theguardian.com/uk/rss"]',
         '["UK","Britain","London","Westminster","Ireland","Scotland","Wales","NHS"]'),

        # ── Health ────────────────────────────────────────────────────────────
        ("Health & Fitness", "health-fitness", "Health", "💪",
         '["https://www.menshealth.com/rss/all.xml/","https://www.runnersworld.com/rss/all.xml"]',
         '["health","fitness","exercise","workout","nutrition","longevity","sleep","recovery"]'),
        ("Mental Health", "mental-health", "Health", "🧘",
         '["https://www.psychologytoday.com/us/front/feed"]',
         '["mental health","anxiety","depression","therapy","mindfulness","burnout","wellbeing","ADHD"]'),
        ("Medical Research", "medical-research", "Health", "🔬",
         '["https://www.sciencedaily.com/rss/health_medicine.xml","https://www.statnews.com/feed/"]',
         '["medical research","clinical trial","drug approval","FDA","cancer","Alzheimer","vaccine","GLP-1"]'),
        ("Nutrition", "nutrition", "Health", "🥗",
         '["https://www.healthline.com/rss/health-news"]',
         '["nutrition","diet","food science","gut health","intermittent fasting","metabolic health","ozempic"]'),

        # ── Entertainment ─────────────────────────────────────────────────────
        ("Gaming", "gaming", "Entertainment", "🎮",
         '["https://feeds.feedburner.com/ign/all-articles","https://www.polygon.com/rss/index.xml","https://kotaku.com/rss"]',
         '["video games","gaming","PlayStation","Xbox","Nintendo","Steam","PC gaming","indie games"]'),
        ("Movies & TV", "movies-tv", "Entertainment", "🎬",
         '["https://feeds.feedburner.com/variety/headlines","https://deadline.com/feed/"]',
         '["movies","TV shows","Netflix","streaming","Hollywood","film","box office","Disney+"]'),
        ("Music", "music", "Entertainment", "🎵",
         '["https://pitchfork.com/rss/news/","https://feeds.feedburner.com/rollingstone/music-news"]',
         '["music","albums","concerts","Spotify","artists","pop","hip-hop","rock","electronic"]'),
        ("Books & Literature", "books-literature", "Entertainment", "📚",
         '["https://feeds.feedburner.com/publishersweekly","https://www.theguardian.com/books/rss"]',
         '["books","literature","novel","author","publishing","bestseller","science fiction","fantasy"]'),
        ("Comics & Anime", "comics-anime", "Entertainment", "🦸",
         '["https://comicbook.com/feed/","https://www.animenewsnetwork.com/all/rss.xml"]',
         '["comics","anime","manga","Marvel","DC","superhero","One Piece","Jujutsu Kaisen"]'),

        # ── Sports ────────────────────────────────────────────────────────────
        ("Soccer / Football", "soccer", "Sports", "⚽",
         '["https://www.theguardian.com/football/rss","https://feeds.feedburner.com/espn/soccer"]',
         '["soccer","football","Premier League","Champions League","FIFA","World Cup","La Liga","Serie A","Bundesliga"]'),
        ("Football (NFL)", "nfl", "Sports", "🏈",
         '["https://www.nfl.com/rss/rsslanding.html","https://feeds.feedburner.com/espn/nfl"]',
         '["NFL","American football","Super Bowl","quarterback","touchdown","fantasy football"]'),
        ("Basketball (NBA)", "nba", "Sports", "🏀",
         '["https://feeds.feedburner.com/espn/nba"]',
         '["NBA","basketball","playoffs","draft","LeBron","Curry","Wembanyama"]'),
        ("Formula 1", "formula-1", "Sports", "🏎️",
         '["https://www.formula1.com/content/fom-website/en/latest/all.rss"]',
         '["Formula 1","F1","Grand Prix","Ferrari","Red Bull","McLaren","Hamilton","Verstappen"]'),
        ("Cricket", "cricket", "Sports", "🏏",
         '["https://www.espncricinfo.com/rss/content/story/feeds/0.xml","https://feeds.bbci.co.uk/sport/cricket/rss.xml"]',
         '["cricket","Test match","IPL","Ashes","ODI","T20","World Cup cricket","BBL"]'),
        ("Rugby", "rugby", "Sports", "🏉",
         '["https://www.rugbyworld.com/feed","https://feeds.bbci.co.uk/sport/rugby-union/rss.xml"]',
         '["rugby","Rugby Union","Rugby League","Six Nations","Super Rugby","World Cup","NRL","State of Origin"]'),
        ("Tennis", "tennis", "Sports", "🎾",
         '["https://www.atptour.com/en/media/rss-feed/xml-feed"]',
         '["tennis","Grand Slam","Wimbledon","US Open","Australian Open","French Open","Djokovic","Alcaraz"]'),
        ("MMA & Boxing", "mma-boxing", "Sports", "🥊",
         '["https://mmajunkie.usatoday.com/feed"]',
         '["MMA","UFC","boxing","fight","Jon Jones","Islam Makhachev"]'),
        ("Golf", "golf", "Sports", "⛳",
         '["https://feeds.feedburner.com/espn/golf"]',
         '["golf","PGA Tour","Masters","Open Championship","LIV Golf","Rory McIlroy","Scottie Scheffler"]'),
        ("Australian Rules Football", "afl", "Sports", "🏟️",
         '["https://www.afl.com.au/rss","https://www.theage.com.au/rss/sport/afl.xml"]',
         '["AFL","Australian Rules Football","Collingwood","Richmond","Geelong","GWS","premiership","finals"]'),

        # ── Lifestyle ─────────────────────────────────────────────────────────
        ("Travel", "travel", "Lifestyle", "✈️",
         '["https://feeds.feedburner.com/lonelyplanet/travel-news","https://www.nomadicmatt.com/feed/"]',
         '["travel","destinations","hotels","flights","backpacking","tourism","visa"]'),
        ("Food & Cooking", "food-cooking", "Lifestyle", "🍳",
         '["https://feeds.feedburner.com/seriouseats/recipes","https://www.eater.com/rss/index.xml"]',
         '["food","cooking","recipes","restaurants","chef","cuisine","michelin"]'),
        ("Home & Garden", "home-garden", "Lifestyle", "🏡",
         '["https://www.apartmenttherapy.com/main.rss","https://www.houzz.com/blog/rss"]',
         '["home improvement","interior design","gardening","DIY","renovation","smart home"]'),
        ("Pets & Animals", "pets-animals", "Lifestyle", "🐾",
         '["https://iheartdogs.com/feed/","https://www.thedodo.com/rss.xml"]',
         '["pets","dogs","cats","animals","wildlife","veterinary"]'),

        # ── Culture ───────────────────────────────────────────────────────────
        ("Philosophy", "philosophy", "Culture", "🤔",
         '["https://aeon.co/feed.rss","https://philosophybites.com/atom.xml"]',
         '["philosophy","ethics","logic","existentialism","stoicism","consciousness"]'),
        ("History", "history", "Culture", "📜",
         '["https://feeds.feedburner.com/HistoryNet","https://www.smithsonianmag.com/rss/history-archaeology/"]',
         '["history","ancient","World War","civilization","historical","documentary"]'),
        ("Art & Design", "art-design", "Culture", "🎨",
         '["https://www.dezeen.com/feed/","https://feeds.feedburner.com/colossal"]',
         '["art","design","architecture","illustration","museum","exhibition","graphic design"]'),
        ("Photography", "photography", "Culture", "📷",
         '["https://petapixel.com/feed/","https://www.dpreview.com/feeds/news"]',
         '["photography","camera","photo","lens","mirrorless","Sony","Nikon","Canon"]'),

        # ── Energy & Environment ──────────────────────────────────────────────
        ("Renewable Energy", "renewable-energy", "Environment", "☀️",
         '["https://cleantechnica.com/feed/","https://www.renewableenergyworld.com/feed/"]',
         '["solar","wind energy","renewable","clean energy","battery storage","grid","hydrogen"]'),
        ("Nuclear Energy", "nuclear-energy", "Environment", "☢️",
         '["https://www.world-nuclear-news.org/rss","https://spectrum.ieee.org/feeds/topic/nuclear-energy.rss"]',
         '["nuclear energy","fusion","fission","reactor","small modular reactor","SMR","thorium"]'),
        ("Conservation", "conservation", "Environment", "🌿",
         '["https://www.mongabay.com/feed/"]',
         '["conservation","wildlife","biodiversity","deforestation","endangered species","rewilding","oceans"]'),
    ]

    for t in topics:
        await db.execute("""
            INSERT OR IGNORE INTO topics (name, slug, category, icon, feed_urls, search_queries)
            VALUES (?, ?, ?, ?, ?, ?)
        """, t)
    await db.commit()
