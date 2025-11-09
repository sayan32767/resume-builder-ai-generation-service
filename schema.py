from pydantic import BaseModel
from typing import List, Optional


class SocialItem(BaseModel):
    name: Optional[str] = None
    link: Optional[str] = None


class PersonalDetails(BaseModel):
    fullName: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    about: Optional[str] = None
    socials: Optional[List[SocialItem]] = None


class ExperienceDates(BaseModel):
    startDate: Optional[str] = None
    endDate: Optional[str] = None


class ExperienceItem(BaseModel):
    companyName: Optional[str] = None
    companyAddress: Optional[str] = None
    position: Optional[str] = None
    dates: Optional[ExperienceDates] = None
    workDescription: Optional[str] = None


class EducationGrades(BaseModel):
    type: Optional[str] = None
    score: Optional[str] = None
    message: Optional[str] = None


class EducationDates(BaseModel):
    startDate: Optional[str] = None
    endDate: Optional[str] = None


class EducationItem(BaseModel):
    name: Optional[str] = None
    degree: Optional[str] = None
    dates: Optional[EducationDates] = None
    location: Optional[str] = None
    grades: Optional[EducationGrades] = None


class SkillItem(BaseModel):
    skillName: Optional[str] = None


class ProjectLink(BaseModel):
    link: Optional[str] = None


class ProjectItem(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    extraDetails: Optional[str] = None
    links: Optional[List[ProjectLink]] = None


class CertificationItem(BaseModel):
    issuingAuthority: Optional[str] = None
    title: Optional[str] = None
    issueDate: Optional[str] = None
    link: Optional[str] = None


class ResumeResponse(BaseModel):
    model_config = {
        "extra": "ignore",
        "exclude_none": True     # ✅ important
    }

    resumeTitle: Optional[str] = None
    resumeType: Optional[str] = None
    personalDetails: Optional[PersonalDetails] = None
    educationDetails: Optional[List[EducationItem]] = None
    skills: Optional[List[SkillItem]] = None
    professionalExperience: Optional[List[ExperienceItem]] = None
    projects: Optional[List[ProjectItem]] = None
    otherExperience: Optional[List[ExperienceItem]] = None
    certifications: Optional[List[CertificationItem]] = None
