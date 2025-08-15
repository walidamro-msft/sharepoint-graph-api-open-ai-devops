# Graph API SharePoint Lister (Python)

A small Python console app that uses MSAL (client credentials) to get an application token for Microsoft Graph and list/download documents in a SharePoint document library (and optional folder path). It can also summarize a downloaded document using Azure OpenAI and then delete the local copy.

## Configuration

Edit `config.json` and fill in your App Registration and SharePoint details:

- tenant_id: Entra ID tenant GUID
- client_id: Application (client) ID GUID
- client_secret: Client secret value
- sharepoint.site_hostname: e.g., `contoso.sharepoint.com`
- sharepoint.site_path: e.g., `/sites/Marketing` or `/teams/Engineering`
- sharepoint.drive_name: Library display name, e.g., `Documents` or `Shared Documents`
- sharepoint.folder_path: Optional folder path within the library, e.g., `Reports/2025/Q3`

You can use `config.example.json` as a reference.

### Azure OpenAI (Azure AI Foundry)

Add your Azure OpenAI settings and summarization prompts to `config.json`:

```
"azure_openai": {
  "endpoint": "https://YOUR-RESOURCE-NAME.openai.azure.com/",
  "api_key": "<AZURE_OPENAI_API_KEY>",
  "deployment": "gpt-4o-mini",
  "api_version": "2024-08-01-preview",
  "max_chars_per_chunk": 12000
},
"prompts": {
  "summarize": {
    "system": "You are a helpful assistant that creates faithful, concise summaries using the user's language and preserving key facts.",
    "user": "Summarize the content focusing on objectives, outcomes, decisions, risks, and action items. Use headings and bullet points. Keep it under 250 words with 3-5 key takeaways."
  }
}
```

Environment variable overrides (recommended for secrets):

- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_CHAT_DEPLOYMENT`
- `AZURE_OPENAI_API_VERSION`

## App permissions (Azure AD / Entra ID)
This app uses application permissions (client credentials). Grant at least:
- Microsoft Graph: `Sites.Read.All` (Application)

Then click “Grant admin consent”.

## How it works

- Auth: MSAL acquires a token via client credentials using the `.default` Graph scope.
- Graph calls:
  1) Resolve site by hostname + path
  2) Resolve library (drive) by name
  3) List items at the drive root or under an optional folder path

## Run locally

1) Ensure `config.json` is filled out (and not using placeholder values).
2) Create a virtual environment and install dependencies.
3) Run the console app. After you select a file, the app will download it, read the text (supports .txt, .pdf, .docx), call the Azure OpenAI model to summarize it, print the summary, and delete the local file.

## Troubleshooting

- 403 errors: Ensure `Sites.Read.All` application permission is granted and admin consented.
- 404 Site/Drive: Check `site_hostname`, `site_path`, and `drive_name` are correct.
- Secret issues: Ensure `client_secret` is the VALUE, not the description.
- OpenAI errors: verify endpoint/deployment/api version are correct for your resource and the key has access.
- PDF/DOCX parsing: Ensure `pdfminer.six` and `python-docx` are installed (they are listed in `requirements.txt`).
