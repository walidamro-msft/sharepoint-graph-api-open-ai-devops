# Grant App Access to a Specific SharePoint Site using Microsoft Graph Explorer

This guide explains how to grant a specific SharePoint Online site to an application that uses the **Sites.Selected** permission model, using **Microsoft Graph Explorer**. It’s designed for beginner Azure admins.

---

## ✅ Prerequisites
- Global Administrator or SharePoint Administrator rights.
- The target app registration exists in Microsoft Entra ID (Azure AD).
- The app has the **Sites.Selected** application permission and **admin consent** granted.
- You know the app’s **Application (client) ID** and (optionally) Display Name.

---

## Step 1 — Open Microsoft Graph Explorer
1. Go to https://developer.microsoft.com/graph/graph-explorer.
2. Sign in with your **Global Admin** account.

---

## Step 2 — Grant Delegated Permissions in Graph Explorer
1. Click **Modify permissions** in the left panel.
2. Search for and consent to:
   - `Sites.FullControl.All` (Delegated)
   - `Sites.Selected` (Delegated)
3. Approve the consent prompts as an admin.

---

## Step 3 — Get the Site ID
1. In Graph Explorer:
   - **Method**: `GET`
   - **URL**:
     ```
     https://graph.microsoft.com/v1.0/sites/{tenant}.sharepoint.com:/sites/{SiteName}
     ```
     Example:
     ```
     https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/ProjectX
     ```
2. Click **Run Query**.
3. Copy the value of `"id"` from the response.  
   Example:
   ```
   contoso.sharepoint.com,44aab5b0-ab16-5w33-9a12-78ed7cd42eb5,916fe481-d5ga-4505-434d-8af938e04egf
   ```

---

## Step 4 — Assign Permission to the App
1. In Graph Explorer:
   - **Method**: `POST`
   - **URL**:
     ```
     https://graph.microsoft.com/v1.0/sites/{siteId}/permissions
     ```
2. **Headers**:
   ```
   Content-Type: application/json
   ```
3. **Body**:
   ```json
   {
     "roles": ["read"],
     "grantedToIdentities": [
       {
         "application": {
           "id": "<AppId>",
           "displayName": "<AppName>"
         }
       }
     ]
   }
   ```
   Replace:
   - `<AppId>` with your app’s Application (client) ID.
   - `<AppName>` with your app’s name.
4. Click **Run Query**.
5. A `201 Created` response means success.

---

## Step 5 — Verify the Permission
1. In Graph Explorer:
   - **Method**: `GET`
   - **URL**:
     ```
     https://graph.microsoft.com/v1.0/sites/{siteId}/permissions
     ```
2. Click **Run Query**.
3. Confirm your app appears with the correct role.

---

## Step 6 — Use the App
- Your app can now call Microsoft Graph for this site using its **own token** (client credentials flow).
- Example:
  ```
  GET https://graph.microsoft.com/v1.0/sites/{siteId}/lists
  ```

---

### ✅ Available Roles
- `read` → Read-only
- `write` → Read and write
- `manage` → Manage lists/libraries
- `fullcontrol` → Full control

---

### 🔍 Notes & Troubleshooting
- **Sites.Selected** by itself grants no access—assignment is required per site.
- To remove access, delete the permission object:
  ```
  DELETE /sites/{siteId}/permissions/{permissionId}
  ```

- For automation, use app-only tokens with client credentials (Postman, Insomnia, or scripts).
