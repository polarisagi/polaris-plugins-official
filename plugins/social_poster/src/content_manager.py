import re

def smart_truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
        
    # Prevent breaking URLs
    urls = [m.span() for m in re.finditer(r'https?://\S+', text)]
    # Prevent breaking hashtags
    hashtags = [m.span() for m in re.finditer(r'#\S+', text)]
    
    protected_ranges = urls + hashtags
    
    cut_idx = max_length - 3
    
    # Check if cut_idx falls inside a protected range
    for start, end in protected_ranges:
        if start < cut_idx < end:
            cut_idx = start # Retreat to the start of the protected element
            break
            
    return text[:cut_idx].strip() + "..."

async def format_content_for_platform(platform: str, content: str) -> str:
    """
    Format content based on platform specifications, including smart truncation.
    """
    if platform == "twitter":
        return smart_truncate(content, 280)
    elif platform == "weibo":
        # Weibo technically supports 2000, but 140 is visually optimal. We truncate at 2000 just in case.
        return smart_truncate(content, 2000)
    elif platform == "xiaohongshu":
        return content # Xiaohongshu supports 1000, usually fine
    elif platform == "douyin":
        # Douyin descriptions should be concise
        return smart_truncate(content, 150)
    elif platform == "instagram":
        return smart_truncate(content, 2200)
    
    return content
