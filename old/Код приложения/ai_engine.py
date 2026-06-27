import json
import re
import urllib.request
import urllib.error
import time

def call_gemini_with_fallback(model_pool, api_key, contents, system_instruction):
    """
    Выполняет прямой HTTP-запрос к официальному API Gemini без использования сторонних SDK.
    Это полностью защищает приложение от системных ошибок кодировки ASCII/UTF-8 на Windows.
    """
    last_exception = None
    for model_name in model_pool:
        for attempt in range(3):
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                headers = {
                    "Content-Type": "application/json"
                }
                
                # Формируем структуру запроса к Google API
                payload = {
                    "contents": [{"parts": [{"text": contents}]}],
                    "systemInstruction": {"parts": [{"text": system_instruction}]},
                    "generationConfig": {
                        "temperature": 0.1
                    }
                }
                
                # Принудительно кодируем в UTF-8 байты, полностью игнорируя локаль Windows
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    text = res_data['candidates'][0]['content']['parts'][0]['text']
                    return text.strip()
                    
            except urllib.error.HTTPError as e:
                status = e.code
                # Если сработал лимит частоты запросов (429) или сервер перегружен (503)
                if status in [429, 503]:
                    time.sleep(2 ** attempt)  # Экспоненциальная пауза: 1с -> 2с -> 4с
                    last_exception = e
                    continue
                
                # Если модель не найдена (404) или не поддерживается, переключаемся на резервную модель
                print(f"[ИИ-Движок]: Модель {model_name} вернула HTTP ошибку {status}. Пробую резерв...")
                last_exception = e
                break
                
            except Exception as e:
                # Обработка сетевых таймаутов
                print(f"[ИИ-Движок]: Сбой сети для {model_name}: {str(e)}")
                last_exception = e
                time.sleep(1)
                
    raise last_exception

def analyze_and_generate(vacancy, config):
    print("\n>>> [DEBUG] СРАБОТАЛ ИСПРАВЛЕННЫЙ ИИ-ФИЛЬТР С КРИТЕРИЯМИ АДЕКВАТНОСТИ 50/50! <<<\n")

    api_key = config.get("api_key", "").strip()
    first_name = config.get("first_name", "Соискатель")
    resume_text = config.get("resume", "")
    
    if not api_key:
        return "ERROR", "Missing API key in configuration", {}

    # Защитная валидация: проверяем, не перепутал ли пользователь поля ввода.
    is_valid_prefix = api_key.startswith("AIza") or api_key.startswith("AQ.")
    has_cyrillic = bool(re.search('[а-яА-Я]', api_key))
    has_spaces = " " in api_key

    if not is_valid_prefix or has_cyrillic or has_spaces:
        return "ERROR", "Invalid API Key! You pasted your Resume into the API Key field by mistake. Please clear 'Лицензия и ИИ-доступ' field and paste the real Gemini API Key.", {}

    raw_title = vacancy.get('title', 'Не указано')
    raw_text = vacancy.get('text', '')

    STAGE1_POOL = ['gemini-3.1-flash-lite', 'gemini-3.1-flash', 'gemini-3.5-flash']
    STAGE2_POOL = ['gemini-3.1-flash-lite', 'gemini-3.1-flash', 'gemini-3.5-flash']

    # Восстановлен оригинальный жесткий фильтр адекватности и отсева
    stage1_system_instruction = (
        "You are an expert career tracker and highly practical job filter agent. Your main goal is to maintain a strict balance: "
        "filter out roughly 50-60% of low-quality, exploitative, scam, or overly demanding vacancies (REDFLAG / reject), "
        "and approve only the best 40-50% of genuine, balanced, professional opportunities that match the candidate's professional profile.\n\n"
        
        "Analyze the job description carefully based on the candidate's resume/skills profile and evaluate the following quality criteria:\n"
        "1. PROFESSION MATCH & ADEQUACY (Strict check):\n"
        "   - The job must be a professional role matching the candidate's background/resume (if provided). "
        "     If the candidate's resume is empty, evaluate the job as a general IT, marketing, sales, administrative, support, creative, or digital role. "
        "     REJECT immediately (set 'is_relevant_profession' to false) if it is manual/unskilled labor: drivers, couriers, cleaners, loaders, etc.\n"
        
        "2. CRITICAL SCAMS & GREY SCHEMES (MANDATORY REJECTION):\n"
        "   - Network marketing (MLM, referral networks) and financial pyramids.\n"
        "   - Esoterics, astrology, numerology, tarot reading, magic.\n"
        "   - Hidden upfront costs (demands to buy starting packs, pay for courses, software, or security deposits).\n"
        "   - Grey crypto schemes, P2P arbitrage, gambling/betting promotion, money laundering, bank card setups.\n"
        
        "3. EXPLOITATION & WORKLOAD FILTERS (Reject if any of these apply):\n"
        "   - Overworked Schedule: Calculate total weekly working hours. If the weekly load strictly exceeds 40-45 hours, mark as REDFLAG (reject). "
        "     (Example: 2/2 shift for 12 hours is ~42 hours per week on average and is OK. But 3/2 for 11 hours, 5/2 for 10 hours, or any load > 45 hours is a REDFLAG).\n"
        "   - Exploitative schedule: Ready to work 24/7, constant unpaid overtime, night shifts without extra compensation.\n"
        "   - Aggressive / Infobusiness marketing slang: Words like 'сильные воронки', 'групповые собеседования', 'массовый набор', 'поток откликов', 'школа лайков'. "
        "     If the vacancy smells like cheap mass selection funnels, reject it.\n"
        "   - Unreasonable ratio of salary to duties (demanding one person to do the job of a designer, copywriter, and marketer for a tiny wage).\n"
        "   - Lack of concreteness: Only contains water about 'success', 'high income', but lists zero actual duties.\n\n"
        
        "Your verdict must be moderately strict. Ignore standard corporate clichés ('work for results', 'stress resistance') as long as duties are clear. "
        "If duties are clear, conditions are fair, schedule is not slavery, and the job passes the filters, set 'is_relevant_profession' to true. "
        "Otherwise, set it to false and write the Russian rejection reason in 'reject_reason'.\n\n"
        
        "You MUST respond ONLY with a valid raw JSON object. Do not include markdown code blocks, do not include explanations, just raw JSON.\n"
        "The JSON object must contain exactly these keys:\n"
        "{\n"
        "  \"is_relevant_profession\": boolean (true if the vacancy is genuine, high-quality, and passes all filter rules. false if it matches any REDFLAG criteria, scam, overwork, or is manual/unskilled labor),\n"
        "  \"reject_reason\": string (detailed, specific reason in Russian if is_relevant_profession is false, describing exactly why it was filtered out, otherwise empty string),\n"
        "  \"extracted_title\": string (cleaned real name of the vacancy in Russian),\n"
        "  \"extracted_company\": string (clean company name in Russian, without OOO/AO),\n"
        "  \"work_format\": \"remote\" | \"office\" | \"hybrid\" | \"unknown\",\n"
        "  \"requires_local_presence\": boolean (true if the text strictly demands physical presence inside Russia, special local citizenship, or contains strict VPN/SB bans for remote workers working from abroad)\n"
        "}"
    )
    
    stage1_prompt = f"Candidate Profile (Resume):\n{resume_text}\n\nJob Title: {raw_title}\n\nPage Text:\n{raw_text[:8000]}"

    try:
        res_text = call_gemini_with_fallback(
            model_pool=STAGE1_POOL,
            api_key=api_key,
            contents=stage1_prompt,
            system_instruction=stage1_system_instruction
        )
        
        clean_json_text = res_text.strip()
        
        markdown_marker = "`" * 3
        
        if clean_json_text.startswith(markdown_marker):
            start_pattern = "^" + re.escape(markdown_marker) + r"(?:json)?\s*"
            clean_json_text = re.sub(start_pattern, '', clean_json_text)
            
            end_pattern = r"\s*" + re.escape(markdown_marker) + "$"
            clean_json_text = re.sub(end_pattern, '', clean_json_text)
            
        clean_json_text = clean_json_text.strip()
        
        if not clean_json_text.startswith("{"):
            match = re.search(r"(\{.*})", clean_json_text, re.DOTALL)
            if match:
                clean_json_text = match.group(1)

        try:
            result_json = json.loads(clean_json_text)
        except json.JSONDecodeError as json_err:
            print(f"\n[DEBUG ERROR] JSON parse failed! Raw AI Response was:\n{res_text}\n")
            raise json_err
        
        extracted_title = result_json.get("extracted_title", raw_title)
        extracted_company = result_json.get("extracted_company", "Не указана")
        extracted_data = {"title": extracted_title, "company": extracted_company}

        # Если вакансия заблокирована ИИ по качеству/адекватности/схемам
        if not result_json.get("is_relevant_profession", True):
            return "REJECTED", result_json.get("reject_reason", "Не прошло фильтр качества вакансий"), extracted_data

        work_format = result_json.get("work_format", "unknown")
        f_remote = config.get("filter_remote")
        f_office = config.get("filter_office")
        f_hybrid = config.get("filter_hybrid")

        # Применяем фильтр формата работы на основе галочек в UI
        if f_remote or f_office or f_hybrid:
            if work_format == "remote" and not f_remote:
                return "REJECTED", "Удаленная работа отключена в настройках приложения.", extracted_data
            elif work_format == "office" and not f_office:
                return "REJECTED", "Работа в офисе отключена в настройках приложения.", extracted_data
            elif work_format == "hybrid" and not f_hybrid:
                return "REJECTED", "Гибридная работа отключена в настройках приложения.", extracted_data

        # Применяем проверку локации (зарубеж / РФ)
        if config.get("filter_no_rf") and result_json.get("requires_local_presence", False):
            return "REJECTED", "Требуется физическое присутствие на территории РФ или запрещен VPN.", extracted_data

    except Exception as e:
        return "ERROR", f"AI Stage 1 system failure: {str(e)}", {}

    stage2_system_instruction = (
        f"You are an HR expert. Write a professional cover letter on behalf of {first_name} in 2-3 short paragraphs. "
        f"The letter MUST be written entirely in Russian language. No fluff. At the very end of the letter, "
        f"MANDATORILY add the closing signature: 'С уважением, {first_name}'."
    )
    stage2_prompt = f"Resume:\n{resume_text}\n\nVacancy: {extracted_title} in company {extracted_company}\nDescription:\n{raw_text[:4000]}"

    try:
        letter_text = call_gemini_with_fallback(
            model_pool=STAGE2_POOL,
            api_key=api_key,
            contents=stage2_prompt,
            system_instruction=stage2_system_instruction
        )
        return "APPROVED", letter_text, extracted_data
    except Exception as e:
        return "ERROR", f"AI Stage 2 system failure: {str(e)}", extracted_data