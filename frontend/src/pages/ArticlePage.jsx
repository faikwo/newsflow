import { useParams, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import api from "../api";
import { ArrowLeft, ExternalLink, Sparkles } from "lucide-react";
import { formatDistanceToNow } from "date-fns";

export default function ArticlePage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [article, setArticle] = useState(null);
  const [summary, setSummary] = useState("");
  const [loadingSummary, setLoadingSummary] = useState(false);

  useEffect(() => {
    // For now navigate to feed - full article view would need scraping
    navigate("/");
  }, []);

  return null;
}
