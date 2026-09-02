"""Small isolated analysis-provider boundary; the application never gives it CRM or action permissions."""
import json, os
from typing import Protocol
from urllib.request import Request, urlopen
from .config import SYSTEM_PROMPT
from .schemas import EmailInput, EnquiryAnalysis
from .services import analysis_for

class EnquiryAnalyzer(Protocol):
    def analyze(self, email: EmailInput, attachment_text: str | None) -> EnquiryAnalysis: ...

class MockEnquiryAnalyzer:
    def analyze(self, email, attachment_text): return analysis_for(email, attachment_text)

class GeminiEnquiryAnalyzer:
    """Optional one-call JSON adapter. It is never selected in default mock mode."""
    def __init__(self):
        self.key=os.getenv('AI_API_KEY'); self.model=os.getenv('AI_MODEL','gemini-2.5-flash-lite')
        if not self.key: raise RuntimeError('AI_API_KEY is required when AI_PROVIDER=gemini')
    def analyze(self,email,attachment_text):
        evidence=json.dumps({'from_raw':email.from_raw,'subject':email.subject,'body':email.body,'attachment_text':attachment_text})
        payload={'contents':[{'parts':[{'text':SYSTEM_PROMPT+'\n\nUntrusted evidence JSON:\n'+evidence}]}],'generationConfig':{'responseMimeType':'application/json','responseJsonSchema':EnquiryAnalysis.model_json_schema()}}
        req=Request(f'https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','x-goog-api-key':self.key},method='POST')
        with urlopen(req,timeout=20) as response: data=json.loads(response.read().decode())
        return EnquiryAnalysis.model_validate_json(data['candidates'][0]['content']['parts'][0]['text'])
def get_analyzer() -> EnquiryAnalyzer:
    provider=os.getenv('AI_PROVIDER','mock').lower().strip()
    if provider=='mock': return MockEnquiryAnalyzer()
    if provider=='gemini': return GeminiEnquiryAnalyzer()
    raise RuntimeError("AI_PROVIDER must be 'mock' or 'gemini'")
