"""
PDF Generator Module
Handles LaTeX compilation for CV and cover letters.
Requires: lualatex (for CV), xelatex (for cover letters)
"""
import os
import re
import subprocess


class PDFGenerator:
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.cv_dir = os.path.join(self.base_dir, "cv")
        self.cover_dir = os.path.join(self.base_dir, "cover_letters")
        
    def compile_cv(self, tex_file="main.tex"):
        """Compile CV with lualatex (required for moderncv with fontawesome5)."""
        tex_path = os.path.join(self.cv_dir, tex_file)
        if not os.path.exists(tex_path):
            return False, f"TeX file not found: {tex_path}"
        
        try:
            subprocess.run(
                ["lualatex", "-interaction=nonstopmode", tex_file],
                cwd=self.cv_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            pdf_file = tex_file.replace(".tex", ".pdf")
            pdf_path = os.path.join(self.cv_dir, pdf_file)
            
            if os.path.exists(pdf_path):
                page_count = self._get_pdf_page_count(pdf_path)
                if page_count == 2:
                    return True, f"CV compiled successfully: {pdf_file} ({page_count} pages)"
                else:
                    return False, f"CV compiled but has {page_count} pages (expected 2)"
            else:
                return False, "PDF not generated. Check LaTeX errors."
                
        except subprocess.TimeoutExpired:
            return False, "LaTeX compilation timed out"
        except FileNotFoundError:
            return False, "lualatex not found. Please install TeX Live or MiKTeX."
    
    def compile_cover_letter(self, tex_file="cover_example.tex"):
        """Compile cover letter with xelatex (required for cover.cls with fontspec)."""
        tex_path = os.path.join(self.cover_dir, tex_file)
        if not os.path.exists(tex_path):
            return False, f"TeX file not found: {tex_path}"
        
        try:
            subprocess.run(
                ["xelatex", "-interaction=nonstopmode", tex_file],
                cwd=self.cover_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            pdf_file = tex_file.replace(".tex", ".pdf")
            pdf_path = os.path.join(self.cover_dir, pdf_file)
            
            if os.path.exists(pdf_path):
                page_count = self._get_pdf_page_count(pdf_path)
                if page_count == 1:
                    return True, f"Cover letter compiled successfully: {pdf_file} ({page_count} page)"
                else:
                    return False, f"Cover letter compiled but has {page_count} pages (expected 1)"
            else:
                return False, "PDF not generated. Check LaTeX errors."
                
        except subprocess.TimeoutExpired:
            return False, "LaTeX compilation timed out"
        except FileNotFoundError:
            return False, "xelatex not found. Please install TeX Live or MiKTeX."
    
    def _get_pdf_page_count(self, pdf_path):
        """Extract page count from PDF file."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            return len(reader.pages)
        except ImportError:
            # Fallback: parse PDF header
            with open(pdf_path, 'rb') as f:
                content = f.read()
                matches = re.findall(rb'/Type\s*/Page[^s]', content)
                return len(matches)
    
    def verify_pdf_text(self, pdf_path):
        """Verify PDF text layer for ATS compatibility."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(pdf_path)
            text = "".join(page.extract_text() or "" for page in reader.pages)
            
            issues = []
            
            # Check for contact info
            if "@" not in text:
                issues.append("Email not found in text layer")
            
            # Check for garbled text
            if "(cid:" in text or "�" in text:
                issues.append("Garbled text detected - font embedding issue")
            
            return {
                "text_length": len(text),
                "has_email": "@" in text,
                "issues": issues,
                "clean": len(issues) == 0
            }
        except ImportError:
            return {"text_length": 0, "has_email": False, "issues": ["pypdf not installed"], "clean": False}
    
    def generate_cv_for_company(self, company_name, profile_data):
        """Generate a tailored CV for a specific company."""
        # Read template
        template_path = os.path.join(self.cv_dir, "main_example.tex")
        if not os.path.exists(template_path):
            return False, "Template not found"
        
        with open(template_path, encoding='utf-8') as f:
            template = f.read()
        
        # Replace placeholders with profile data
        cv_content = self._fill_template(template, profile_data)
        
        # Write company-specific CV
        output_file = f"main_{company_name.lower().replace(' ', '_')}.tex"
        output_path = os.path.join(self.cv_dir, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cv_content)
        
        return True, output_file
    
    def generate_cover_for_company(self, company_name, role_name, profile_data, job_description):
        """Generate a tailored cover letter for a specific company/role."""
        template_path = os.path.join(self.cover_dir, "cover_example.tex")
        if not os.path.exists(template_path):
            return False, "Template not found"
        
        with open(template_path, encoding='utf-8') as f:
            template = f.read()
        
        # Replace placeholders
        cover_content = self._fill_template(template, profile_data)
        
        # Write company-specific cover letter
        safe_company = company_name.lower().replace(' ', '_')
        safe_role = role_name.lower().replace(' ', '_')
        output_file = f"cover_{safe_company}_{safe_role}.tex"
        output_path = os.path.join(self.cover_dir, output_file)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(cover_content)
        
        return True, output_file
    
    def _fill_template(self, template, data):
        """Fill template placeholders with profile data."""
        replacements = {
            "[YOUR_NAME]": data.get("name", "[YOUR_NAME]"),
            "[First]": data.get("first_name", "[First]"),
            "[Last]": data.get("last_name", "[Last]"),
            "[Your Address, City, Country]": data.get("address", "[Your Address]"),
            "[+XX XXXXXXXXXX]": data.get("phone", "[+XX XXXXXXXXXX]"),
            "[your.email@example.com]": data.get("email", "[your.email@example.com]"),
            "[https://linkedin.com/in/your-profile]": data.get("linkedin", "[linkedin_url]"),
            "[https://github.com/your-username]": data.get("github", "[github_url]"),
        }
        
        for placeholder, value in replacements.items():
            template = template.replace(placeholder, value)
        
        return template


if __name__ == "__main__":
    generator = PDFGenerator()
    print("PDF Generator initialized.")
    print(f"CV directory: {generator.cv_dir}")
    print(f"Cover letter directory: {generator.cover_dir}")
