"""
Application Tracking Module
Tracks job applications and their outcomes.
"""
import csv
import json
import os
from datetime import datetime


class ApplicationTracker:
    """Tracks job applications and their outcomes."""
    
    def __init__(self, base_dir=None):
        self.base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
        self.tracker_file = os.path.join(self.base_dir, "job_search_tracker.csv")
        self.applications_dir = os.path.join(self.base_dir, "applications")
        
        # Create applications directory if it doesn't exist
        os.makedirs(self.applications_dir, exist_ok=True)
        
        # Initialize CSV if it doesn't exist
        if not os.path.exists(self.tracker_file):
            self._init_tracker()
    
    def _init_tracker(self):
        """Initialize the tracker CSV file."""
        headers = [
            "company", "role", "date_applied", "status",
            "cv_file", "cover_letter_file", "job_url",
            "overall_score", "verdict", "notes"
        ]
        
        with open(self.tracker_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
    
    def add_application(self, company, role, job_url="", cv_file="", 
                       cover_letter_file="", overall_score=0, verdict="", notes=""):
        """Add a new application to the tracker."""
        date_applied = datetime.now().strftime("%Y-%m-%d")
        status = "Applied"
        
        row = [
            company, role, date_applied, status,
            cv_file, cover_letter_file, job_url,
            overall_score, verdict, notes
        ]
        
        with open(self.tracker_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(row)
        
        # Create application archive directory
        archive_dir = self._get_archive_dir(company, role)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Save application details
        details = {
            "company": company,
            "role": role,
            "date_applied": date_applied,
            "status": status,
            "job_url": job_url,
            "cv_file": cv_file,
            "cover_letter_file": cover_letter_file,
            "overall_score": overall_score,
            "verdict": verdict,
            "notes": notes
        }
        
        details_file = os.path.join(archive_dir, "application_details.json")
        with open(details_file, 'w', encoding='utf-8') as f:
            json.dump(details, f, indent=2, ensure_ascii=False)
        
        return True, f"Application added: {company} - {role}"
    
    def update_status(self, company, role, new_status, notes=""):
        """Update the status of an application."""
        if not os.path.exists(self.tracker_file):
            return False, "Tracker file not found"
        
        rows = []
        updated = False
        
        with open(self.tracker_file, encoding='utf-8') as f:
            reader = csv.reader(f)
            headers = next(reader)
            
            for row in reader:
                if len(row) >= 2 and row[0] == company and row[1] == role:
                    row[3] = new_status  # Status column
                    if notes:
                        row[9] = notes  # Notes column
                    updated = True
                rows.append(row)
        
        if updated:
            with open(self.tracker_file, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                writer.writerows(rows)
            
            # Update archive details
            archive_dir = self._get_archive_dir(company, role)
            details_file = os.path.join(archive_dir, "application_details.json")
            
            if os.path.exists(details_file):
                with open(details_file, encoding='utf-8') as f:
                    details = json.load(f)
                
                details["status"] = new_status
                details["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if notes:
                    details["notes"] = notes
                
                with open(details_file, 'w', encoding='utf-8') as f:
                    json.dump(details, f, indent=2, ensure_ascii=False)
            
            return True, f"Status updated to: {new_status}"
        else:
            return False, f"Application not found: {company} - {role}"
    
    def get_application(self, company, role):
        """Get details for a specific application."""
        archive_dir = self._get_archive_dir(company, role)
        details_file = os.path.join(archive_dir, "application_details.json")
        
        if os.path.exists(details_file):
            with open(details_file, encoding='utf-8') as f:
                return json.load(f)
        return None
    
    def list_applications(self, status_filter=None):
        """List all applications, optionally filtered by status."""
        if not os.path.exists(self.tracker_file):
            return []
        
        applications = []
        
        with open(self.tracker_file, encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                if status_filter is None or row.get("status") == status_filter:
                    applications.append(row)
        
        return applications
    
    def get_statistics(self):
        """Get application statistics."""
        applications = self.list_applications()
        
        stats = {
            "total": len(applications),
            "by_status": {},
            "average_score": 0
        }
        
        scores = []
        for app in applications:
            status = app.get("status", "Unknown")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
            
            try:
                score = float(app.get("overall_score", 0))
                if score > 0:
                    scores.append(score)
            except (TypeError, ValueError):
                pass
        
        if scores:
            stats["average_score"] = round(sum(scores) / len(scores), 1)
        
        return stats
    
    def _get_archive_dir(self, company, role):
        """Get archive directory path for an application."""
        import re
        safe_company = re.sub(r'[^\w\-]', '_', company).strip('_')[:50]
        safe_role = re.sub(r'[^\w\-]', '_', role).strip('_')[:50]
        return os.path.join(self.applications_dir, f"{safe_company}_{safe_role}")
    
    def save_job_materials(self, company, role, job_description, 
                          cv_content=None, cover_letter_content=None):
        """Save job materials to the application archive."""
        archive_dir = self._get_archive_dir(company, role)
        os.makedirs(archive_dir, exist_ok=True)
        
        # Save job description
        jd_file = os.path.join(archive_dir, "job_description.txt")
        with open(jd_file, 'w', encoding='utf-8') as f:
            f.write(job_description)
        
        # Save CV if provided
        if cv_content:
            cv_file = os.path.join(archive_dir, "cv.tex")
            with open(cv_file, 'w', encoding='utf-8') as f:
                f.write(cv_content)
        
        # Save cover letter if provided
        if cover_letter_content:
            cl_file = os.path.join(archive_dir, "cover_letter.tex")
            with open(cl_file, 'w', encoding='utf-8') as f:
                f.write(cover_letter_content)
        
        return True, f"Materials saved to {archive_dir}"


if __name__ == "__main__":
    tracker = ApplicationTracker()
    print("Application Tracker initialized.")
    print(f"Tracker file: {tracker.tracker_file}")
    print(f"Applications directory: {tracker.applications_dir}")
    
    # Test adding an application
    # tracker.add_application("Test Company", "Software Engineer", "https://example.com")
    # print(tracker.list_applications())
