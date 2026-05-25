    def _get_credentials(self, mode: str = "sandbox") -> str:
        """
        Fetch Duffel credentials from Tools Server using curl-based helper.
        
        Args:
            mode: "sandbox" or "live"
        
        Returns:
            API key string
        """
        try:
            cred_id = CREDENTIAL_SANDBOX if mode == "sandbox" else CREDENTIAL_LIVE
            api_key = get_api_key(cred_id)
            
            key_preview = f"{api_key[:12]}...{api_key[-4:]}"
            mode_display = "LIVE" if api_key.startswith("duffel_live_") else "SANDBOX"
            print(f"✓ Fetched Duffel key [{mode_display}]: {key_preview}", file=sys.stderr)
            
            return api_key
            
        except Exception as e:
            print(f"⚠️  Failed to fetch credentials: {e}", file=sys.stderr)
            # Fallback to environment variable
            env_key = os.environ.get("DUFFEL_API_KEY")
            if env_key:
                print(f"⚠️  Using DUFFEL_API_KEY from environment", file=sys.stderr)
                return env_key
            raise DuffelError(
                f"Could not fetch Duffel API key. Ensure Tools Server is running and credential '{cred_id}' exists.",
                status_code=0
            )