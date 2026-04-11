"""Gemini integration for analyzing listing condition."""
import google.genai as genai
import logging
import config
import time
import re

logger = logging.getLogger(__name__)


class ConditionAnalyzer:
    """Uses Gemini to analyze listing descriptions and classify condition."""

    def __init__(self):
        """Initialize Gemini client."""
        if not config.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        self.client = genai.Client(api_key=config.GEMINI_API_KEY)
        self.model = config.GEMINI_MODEL

    def analyze_condition(self, description):
        """
        Analyze listing description and classify condition.

        Args:
            description: The listing description text

        Returns:
            str: "Excellent", "Good", or "Fair"
        """
        if not description or len(description.strip()) == 0:
            logger.warning("Empty description provided, defaulting to 'Good'")
            return "Good"

        prompt = f"""Analyze the following Porsche listing description and classify the vehicle's condition as one of three categories: Excellent, Good, or Fair.

Consider factors such as:
- Overall condition mentions (pristine, excellent, good, fair, needs work, etc.)
- Maintenance history
- Wear and tear indicators
- Restoration status
- Damage or issues mentioned
- Overall presentation quality
- Missing parts indicators: words like "stripped", "missing", "removed", "absent", "gone", "not included", "without", "lacks"
- Broken/damaged parts indicators: words like "broken", "cracked", "damaged", "bent", "dented", "faulty", "non-functional", "not working", "inoperable", "seized", "worn out"
- Rust/corrosion indicators: words like "rust", "rusty", "corrosion", "corroded", "oxidized", "rust holes", "rust damage"
- Mismatched parts indicators: words like "mismatched", "non-matching", "incorrect", "wrong", "replacement", "aftermarket", "non-original"
- Incomplete/partial indicators: words like "incomplete", "partial", "unfinished", "project", "needs assembly", "disassembled", "taken apart"
- Structural issues: words like "frame damage", "structural rust", "bent frame", "collision damage", "accident damage"

Pay special attention to negative indicators. A listing with missing parts, broken components, significant rust, or structural issues should be classified as "Fair" or "Good" at best, even if other aspects seem positive.

Return ONLY one word: Excellent, Good, or Fair.

Description:
{description[:2000]}

Condition:"""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            condition = response.text.strip()

            condition_lower = condition.lower()
            if 'excellent' in condition_lower:
                return "Excellent"
            elif 'good' in condition_lower:
                return "Good"
            elif 'fair' in condition_lower:
                return "Fair"
            else:
                logger.warning(f"Unexpected condition response: {condition}, defaulting to 'Good'")
                return "Good"

        except Exception as e:
            logger.error(f"Error analyzing condition: {e}")
            return "Good"

    def analyze_batch(self, descriptions, delay=0.5):
        """
        Analyze multiple descriptions with rate limiting.

        Args:
            descriptions: List of description strings
            delay: Seconds to wait between API calls

        Returns:
            list: List of condition classifications
        """
        conditions = []
        for i, desc in enumerate(descriptions):
            if i > 0:
                time.sleep(delay)
            condition = self.analyze_condition(desc)
            conditions.append(condition)
        return conditions

    def analyze_batch_parallel(self, descriptions):
        """
        Analyze multiple descriptions efficiently using a single prompt.

        Args:
            descriptions: List of description strings

        Returns:
            list: List of condition classifications
        """
        if not descriptions:
            return []

        descriptions_text = ""
        for i, desc in enumerate(descriptions, 1):
            desc_limited = desc[:1500] if desc else ""
            descriptions_text += f"\n\nListing {i}:\n{desc_limited}\n---"

        prompt = f"""Analyze the following Porsche listing descriptions and classify each vehicle's condition as one of three categories: Excellent, Good, or Fair.

For each listing, consider factors such as:
- Overall condition mentions (pristine, excellent, good, fair, needs work, etc.)
- Maintenance history
- Wear and tear indicators
- Restoration status
- Damage or issues mentioned
- Overall presentation quality
- Missing parts indicators: words like "stripped", "missing", "removed", "absent", "gone", "not included", "without", "lacks"
- Broken/damaged parts indicators: words like "broken", "cracked", "damaged", "bent", "dented", "faulty", "non-functional", "not working", "inoperable", "seized", "worn out"
- Rust/corrosion indicators: words like "rust", "rusty", "corrosion", "corroded", "oxidized", "rust holes", "rust damage"
- Mismatched parts indicators: words like "mismatched", "non-matching", "incorrect", "wrong", "replacement", "aftermarket", "non-original"
- Incomplete/partial indicators: words like "incomplete", "partial", "unfinished", "project", "needs assembly", "disassembled", "taken apart"
- Structural issues: words like "frame damage", "structural rust", "bent frame", "collision damage", "accident damage"

Pay special attention to negative indicators. A listing with missing parts, broken components, significant rust, or structural issues should be classified as "Fair" or "Good" at best, even if other aspects seem positive.

Return your analysis as a numbered list with exactly one word per listing: Excellent, Good, or Fair.

Listings:{descriptions_text}

Respond with only the conditions, one per line, numbered 1, 2, 3, etc."""

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )
            result_text = response.text.strip()

            conditions = []
            lines = result_text.split('\n')
            for line in lines:
                line = line.strip()
                line = re.sub(r'^\d+[\.\)]\s*', '', line, flags=re.IGNORECASE)
                line_lower = line.lower()
                if 'excellent' in line_lower:
                    conditions.append("Excellent")
                elif 'good' in line_lower:
                    conditions.append("Good")
                elif 'fair' in line_lower:
                    conditions.append("Fair")
                else:
                    conditions.append("Good")

            while len(conditions) < len(descriptions):
                conditions.append("Good")

            return conditions[:len(descriptions)]

        except Exception as e:
            logger.error(f"Error in batch analysis: {e}")
            return self.analyze_batch(descriptions)
