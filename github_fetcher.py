# NOT IN USE CURRENTLY

import requests

def fetch_github_data(username):
    url = f"https://api.github.com/users/{username}/repos"
    r = requests.get(url).json()

    repos = []
    for repo in r:
        repos.append({
            "name": repo.get("name"),
            "description": repo.get("description"),
            "language": repo.get("language"),
            "stars": repo.get("stargazers_count"),
            "url": repo.get("html_url"),
        })

    return repos
