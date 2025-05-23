"""
OpenAI implementation of the BIM Agent for the BIM AI Management Dashboard.
This module provides OpenAI-based AI capabilities for processing BIM data.
"""
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.entities.stakeholder import StakeholderGroup

# Configure logging
logger = logging.getLogger(__name__)


class OpenAIBIMAgent:
    """
    BIM Agent implementation using OpenAI API
    Includes stakeholder identification and enhanced interaction with BIM data
    """

    def __init__(self):
        """Initialize the OpenAI BIM Agent."""
        self.enhanced_mode = False
        self.identified_stakeholder = None
        self.conversation_history = []
        self.bim_data = None
        self.client = None

        try:
            import openai

            self.client = openai.OpenAI()
            logger.debug("OpenAI client initialized successfully")
        except (ImportError, Exception) as e:
            logger.error(f"Error initializing OpenAI client: {e}")
            self.client = None

    def toggle_enhanced_mode(self, enabled: bool = True) -> bool:
        """Toggle between standard and enhanced AI modes"""
        self.enhanced_mode = enabled
        logger.info(f"Enhanced mode {'enabled' if enabled else 'disabled'}")
        return self.enhanced_mode

    def identify_stakeholder(self, messages: List[Dict]) -> Optional[str]:
        """
        Identify which stakeholder group the user belongs to based on their messages
        Returns the stakeholder group identifier
        """
        if not self.client:
            logger.error("Cannot identify stakeholder: OpenAI client not available")
            return None

        try:
            # Extract user messages
            user_text = " ".join(
                [msg["content"] for msg in messages if msg["role"] == "user"]
            )

            if not user_text:
                return None

            # Prepare system message for stakeholder identification
            system_message = (
                "Identify which of the following real estate stakeholder groups the person belongs to "
                "based on their messages: Tenant/Buyer, Broker, Landlord, "
                "Property Manager, Appraiser, Mortgage Broker, or Investor. "
                "Return only the stakeholder type as a single word or phrase."
            )

            # Call OpenAI API for stakeholder identification
            response = self.client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": user_text},
                ],
                max_tokens=20,
                temperature=0.1,
            )

            stakeholder_text = response.choices[0].message.content.strip().lower()

            # Map the returned text to our stakeholder groups
            mapping = {
                "tenant": StakeholderGroup.TENANT_BUYER,
                "buyer": StakeholderGroup.TENANT_BUYER,
                "tenant/buyer": StakeholderGroup.TENANT_BUYER,
                "broker": StakeholderGroup.BROKER,
                "landlord": StakeholderGroup.LANDLORD,
                "property manager": StakeholderGroup.PROPERTY_MANAGER,
                "appraiser": StakeholderGroup.APPRAISER,
                "mortgage broker": StakeholderGroup.MORTGAGE_BROKER,
                "investor": StakeholderGroup.INVESTOR,
            }

            # Find the closest match
            for key, value in mapping.items():
                if key in stakeholder_text:
                    self.identified_stakeholder = value
                    logger.debug(f"Identified stakeholder: {value}")
                    return value

            # Default to investor if no match found
            self.identified_stakeholder = StakeholderGroup.INVESTOR
            return StakeholderGroup.INVESTOR

        except Exception as e:
            logger.error(f"Error identifying stakeholder: {e}")
            return None

    # Define regex patterns for inappropriate content
    INAPPROPRIATE_PATTERNS = [
        r"(?i)(hack|exploit|bypass|crack|steal|illegal|injection|attack)",
        r"(?i)(passport|ssn|social security|credit.?card|bank.?account)",
        r"(?i)(phish|malware|ransomware|rootkit|spyware|trojan)",
        r"(?i)(profanity|obscenity|explicit content|nsfw|porn)",
        r"(?i)(gambling|betting|casino|lottery|slots)",
        r"(?i)(drug|narcotic|cocaine|heroin|meth)",
    ]

    def _check_message_appropriateness(self, message: str) -> bool:
        """
        Check if the user message is appropriate for the BIM AI assistant context
        using multiple layers of filtering.
        Returns True if appropriate, False if inappropriate.
        """
        import re

        # 1. First check - reject empty or extremely short messages
        if not message or len(message.strip()) < 2:
            logger.warning("Rejected empty or too short message")
            return False

        # 2. Second check - reject obviously inappropriate content via regex
        for pattern in self.INAPPROPRIATE_PATTERNS:
            if re.search(pattern, message):
                logger.warning(f"Message rejected by regex pattern: {pattern}")
                return False

        try:
            # 3. Third check - use OpenAI's moderation endpoint
            moderation = self.client.moderations.create(input=message)
            if moderation.results[0].flagged:
                # Log which categories were flagged
                flagged_categories = []
                categories = moderation.results[0].categories
                for category, flagged in categories.items():
                    if flagged:
                        flagged_categories.append(category)

                logger.warning(
                    f"Message flagged by OpenAI moderation API: {flagged_categories}"
                )
                return False

            # 4. Fourth check - more nuanced appropriateness check
            # Only perform if message passes the first three layers
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a strict content filter for a professional real estate platform. "
                        "Assess if the following message is appropriate and "
                        "related to buildings, real estate, property investments, "
                        "construction, architecture, or blockchain tokenization. "
                        "Respond with only 'APPROPRIATE' or 'INAPPROPRIATE'. "
                        "Be conservative - if there's any doubt, classify as INAPPROPRIATE.",
                    },
                    {"role": "user", "content": message},
                ],
                max_tokens=10,
                temperature=0.0,
            )

            result = response.choices[0].message.content.strip().upper()
            appropriate = "APPROPRIATE" in result

            if not appropriate:
                logger.warning("Message rejected by GPT content filter")

            return appropriate

        except Exception as e:
            logger.error(f"Error checking message appropriateness: {e}")
            # Default to rejecting the message if any error occurs during checks
            # This is safer than allowing potentially harmful content
            return False

    def process_message(
        self, message: str, bim_data: Optional[Dict] = None
    ) -> Tuple[str, Dict]:
        """
        Process a user message and return an AI response
        Uses OpenAI API in standard mode, and a more advanced processing in enhanced mode

        Args:
            message: User message text
            bim_data: Optional BIM data for context

        Returns:
            Tuple containing (response_text, metadata)
        """
        # Update conversation history
        self.conversation_history.append({"role": "user", "content": message})

        # Update BIM data if provided
        if bim_data:
            self.bim_data = bim_data

        # If OpenAI client is not available, return error message
        if not self.client:
            error_msg = "AI service is currently unavailable. Please check your API key configuration."
            self.conversation_history.append(
                {"role": "assistant", "content": error_msg}
            )
            return error_msg, {"error": "api_unavailable"}

        try:
            # Check if the message is appropriate for the BIM AI context
            is_appropriate = self._check_message_appropriateness(message)

            if not is_appropriate:
                response_text = (
                    "I'm a BIM AI assistant focused on providing information about buildings, real "
                    "estate, and property investments. Please ask questions related to these "
                    "topics so I can help you effectively. For instance, you could ask about "
                    "building specifications, property valuations, or investment strategies."
                )
                self.conversation_history.append(
                    {"role": "assistant", "content": response_text}
                )
                return response_text, {"filtered": True}

            # Identify stakeholder if not already identified
            if not self.identified_stakeholder and len(self.conversation_history) >= 1:
                self.identify_stakeholder(self.conversation_history)

            # Prepare system message based on mode and stakeholder
            if self.enhanced_mode:
                system_message = self._get_enhanced_system_message()
            else:
                system_message = self._get_standard_system_message()

            # Add content guidelines
            content_guidelines = (
                "IMPORTANT: You are a professional BIM AI assistant for real estate. "
                "Only answer questions related to buildings, real estate, property investments, "
                "architecture, construction, blockchain tokenization, and related professional topics. "
                "If asked about inappropriate topics, politely redirect the conversation to "
                "building information modeling and real estate investment topics. "
                "Do not engage with or acknowledge inappropriate requests."
            )
            system_message = content_guidelines + "\n\n" + system_message

            # Add BIM context if available
            if self.bim_data:
                bim_context = (
                    f"BIM data available: {self.bim_data.get('summary', 'None')}"
                )
                system_message += f"\n\n{bim_context}"

            # Add stakeholder context if identified
            if self.identified_stakeholder:
                stakeholder_name = StakeholderGroup.get_name(
                    self.identified_stakeholder
                )
                stakeholder_context = (
                    f"The user appears to be a {stakeholder_name}. Tailor your responses "
                    "accordingly."
                )
                system_message += f"\n\n{stakeholder_context}"

            # Prepare messages for the API call
            messages = [{"role": "system", "content": system_message}]

            # Add conversation history, but limit to last 10 messages to avoid token limits
            messages.extend(self.conversation_history[-10:])

            # Call OpenAI API
            response = self.client.chat.completions.create(
                model="gpt-4o" if self.enhanced_mode else "gpt-3.5-turbo",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )

            response_text = response.choices[0].message.content

            # Update conversation history with the AI response
            self.conversation_history.append(
                {"role": "assistant", "content": response_text}
            )

            # Prepare metadata for the frontend
            metadata = {
                "enhanced_mode": self.enhanced_mode,
                "stakeholder": self.identified_stakeholder,
                "stakeholder_name": (
                    StakeholderGroup.get_name(self.identified_stakeholder)
                    if self.identified_stakeholder
                    else None
                ),
                "model": "gpt-4o" if self.enhanced_mode else "gpt-3.5-turbo",
            }

            return response_text, metadata

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            error_msg = "Sorry, I encountered an error processing your message. Please try again."
            self.conversation_history.append(
                {"role": "assistant", "content": error_msg}
            )
            return error_msg, {"error": str(e)}

    def _get_standard_system_message(self) -> str:
        """Get the system message for standard mode"""
        return (
            "You are a helpful AI assistant for a blockchain-powered real estate tokenization platform. "
            "You help users understand Building Information Modeling (BIM) data and provide insights "
            "about properties on the platform. Be concise and direct in your responses."
        )

    def _get_enhanced_system_message(self) -> str:
        """Get the system message for enhanced mode"""
        return (
            "You are an advanced BIM AI assistant for a blockchain-powered real estate tokenization platform. "
            "You have deep expertise in Building Information Modeling (BIM) methodology, IFC file structures, "
            "and blockchain property tokenization. You provide detailed, stakeholder-specific insights and can "
            "interface directly with building models to extract valuable property information."
            "\n\n"
            "When analyzing BIM data, consider spatial relationships, material specifications, structural "
            "integrity, energy efficiency metrics, and compliance with building codes. For blockchain "
            "aspects, consider tokenization strategies, smart contract functionality, transaction security, "
            "and regulatory compliance."
            "\n\n"
            "Adapt your response style and technical depth based on the identified stakeholder group:"
            "- For Tenants/Buyers: Focus on livability, amenities, and future value"
            "- For Brokers: Emphasize marketability and comparable properties"
            "- For Landlords: Highlight maintenance needs and operational efficiency"
            "- For Property Managers: Focus on building systems and maintenance schedules"
            "- For Appraisers: Provide detailed valuation metrics and comparable analysis"
            "- For Mortgage Brokers: Discuss financing implications and risk assessments"
            "- For Investors: Analyze ROI potential, tokenization value, and market trends"
        )