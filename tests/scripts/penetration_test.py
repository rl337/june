#!/usr/bin/env python3
"""
Penetration Testing Script for June Agent System

⚠️ **OBSOLETE:** This script is obsolete in its current form because it tests
the gateway service, which has been removed as part of the refactoring. The
gateway service was removed to achieve a minimal architecture with direct
gRPC communication between services.

**Original Purpose:**
Performs automated and manual security testing across all services via the
gateway HTTP API endpoints.

**Status:** This script is kept for reference but is not functional in its
current form. All tests target the removed gateway service (`GATEWAY_URL`).
The script could potentially be updated to test the remaining services
(telegram, discord) which may have HTTP endpoints, or adapted to test gRPC
services using different security testing approaches.
"""
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import grpc
import httpx
from june_grpc_api import asr, llm, tts

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class PenetrationTester:
    """Comprehensive penetration testing for June Agent system."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.findings: List[Dict[str, Any]] = []
        self.test_results: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "tests_run": 0,
            "vulnerabilities_found": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "findings": [],
        }

    def add_finding(
        self,
        severity: str,
        title: str,
        description: str,
        service: str,
        endpoint: str = "",
        evidence: str = "",
        recommendation: str = "",
    ):
        """Add a security finding."""
        finding = {
            "severity": severity.upper(),
            "title": title,
            "description": description,
            "service": service,
            "endpoint": endpoint,
            "evidence": evidence,
            "recommendation": recommendation,
            "timestamp": datetime.now().isoformat(),
        }
        self.findings.append(finding)
        self.test_results["findings"].append(finding)
        self.test_results["vulnerabilities_found"] += 1
        self.test_results[severity.lower()] += 1
        print(f"[{severity.upper()}] {title} - {service}")

    async def test_cors_configuration(self):
        """Test CORS configuration for vulnerabilities."""
        print("\n[TEST] CORS Configuration Testing...")
        self.test_results["tests_run"] += 1

        async with httpx.AsyncClient() as client:
            # Test with malicious origin
            headers = {
                "Origin": "https://evil.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization, Content-Type",
            }

            try:
                response = await client.options(
                    f"{self.base_url}/api/v1/llm/generate", headers=headers, timeout=5.0
                )

                # Check if CORS allows all origins
                if "Access-Control-Allow-Origin" in response.headers:
                    acao = response.headers["Access-Control-Allow-Origin"]
                    if acao == "*" or acao == "https://evil.com":
                        self.add_finding(
                            severity="HIGH",
                            title="Overly Permissive CORS Configuration",
                            description=f"CORS allows requests from any origin. Current setting: {acao}",
                            service="Gateway",
                            endpoint="/api/v1/llm/generate",
                            evidence=f"Response header: Access-Control-Allow-Origin: {acao}",
                            recommendation="Restrict CORS to specific trusted domains. Remove wildcard (*) when allow_credentials=True.",
                        )
            except Exception as e:
                print(f"  Error testing CORS: {e}")

    async def test_authentication_bypass(self):
        """Test for authentication bypass vulnerabilities."""
        print("\n[TEST] Authentication Bypass Testing...")
        self.test_results["tests_run"] += 1

        # Test endpoints that should require authentication
        protected_endpoints = [
            "/api/v1/llm/generate",
            "/api/v1/tts/speak",
            "/api/v1/audio/transcribe",
            "/admin/users",
            "/admin/conversations",
        ]

        async with httpx.AsyncClient() as client:
            for endpoint in protected_endpoints:
                try:
                    # Test without authentication
                    response = await client.post(
                        f"{self.base_url}{endpoint}", json={"test": "data"}, timeout=5.0
                    )

                    if response.status_code == 200:
                        self.add_finding(
                            severity="CRITICAL",
                            title=f"Authentication Bypass - {endpoint}",
                            description=f"Endpoint {endpoint} accepts requests without authentication",
                            service="Gateway",
                            endpoint=endpoint,
                            evidence=f"Status code: {response.status_code}, Response: {response.text[:200]}",
                            recommendation="Ensure all protected endpoints require valid JWT tokens",
                        )
                    elif response.status_code == 401 or response.status_code == 403:
                        print(f"  ✓ {endpoint} properly requires authentication")
                    else:
                        print(f"  ? {endpoint} returned {response.status_code}")

                except Exception as e:
                    print(f"  Error testing {endpoint}: {e}")

                # Test with invalid token
                try:
                    headers = {"Authorization": "Bearer invalid_token_12345"}
                    response = await client.post(
                        f"{self.base_url}{endpoint}",
                        json={"test": "data"},
                        headers=headers,
                        timeout=5.0,
                    )

                    if response.status_code == 200:
                        self.add_finding(
                            severity="CRITICAL",
                            title=f"Invalid Token Accepted - {endpoint}",
                            description=f"Endpoint {endpoint} accepts invalid JWT tokens",
                            service="Gateway",
                            endpoint=endpoint,
                            evidence=f"Status code: {response.status_code}",
                            recommendation="Ensure JWT token validation properly rejects invalid tokens",
                        )
                except Exception as e:
                    print(f"  Error testing invalid token on {endpoint}: {e}")

    async def test_sql_injection(self):
        """Test for SQL injection vulnerabilities."""
        print("\n[TEST] SQL Injection Testing...")
        self.test_results["tests_run"] += 1

        # Common SQL injection payloads
        sql_payloads = [
            "' OR '1'='1",
            "'; DROP TABLE users--",
            "' UNION SELECT NULL--",
            "1' OR '1'='1",
            "admin'--",
            "' OR 1=1--",
        ]

        # Test endpoints that might be vulnerable
        test_endpoints = [
            ("/auth/login", {"username": "test", "password": "test"}),
            ("/admin/users/search", {"query": "test"}),
        ]

        async with httpx.AsyncClient() as client:
            for endpoint, base_data in test_endpoints:
                for payload in sql_payloads:
                    try:
                        # Inject payload into various fields
                        test_data = base_data.copy()
                        if "username" in test_data:
                            test_data["username"] = payload
                        if "query" in test_data:
                            test_data["query"] = payload

                        response = await client.post(
                            f"{self.base_url}{endpoint}", json=test_data, timeout=5.0
                        )

                        # Check for SQL error messages
                        response_text = response.text.lower()
                        sql_errors = [
                            "sql syntax",
                            "mysql",
                            "postgresql",
                            "sqlite",
                            "database error",
                            "syntax error",
                        ]

                        if any(error in response_text for error in sql_errors):
                            self.add_finding(
                                severity="HIGH",
                                title=f"Potential SQL Injection - {endpoint}",
                                description=f"SQL error message detected in response to SQL injection payload",
                                service="Gateway",
                                endpoint=endpoint,
                                evidence=f"Payload: {payload}, Response contains SQL error",
                                recommendation="Use parameterized queries for all database operations. Validate and sanitize all user inputs.",
                            )
                            break

                    except Exception as e:
                        print(f"  Error testing SQL injection on {endpoint}: {e}")

    async def test_xss_vulnerabilities(self):
        """Test for Cross-Site Scripting (XSS) vulnerabilities."""
        print("\n[TEST] XSS Vulnerability Testing...")
        self.test_results["tests_run"] += 1

        xss_payloads = [
            "<script>alert('XSS')</script>",
            "<img src=x onerror=alert('XSS')>",
            "javascript:alert('XSS')",
            "<svg onload=alert('XSS')>",
        ]

        # Test endpoints that reflect user input
        test_endpoints = [
            ("/api/v1/llm/generate", {"prompt": "test"}),
        ]

        async with httpx.AsyncClient() as client:
            for endpoint, base_data in test_endpoints:
                for payload in xss_payloads:
                    try:
                        test_data = base_data.copy()
                        if "prompt" in test_data:
                            test_data["prompt"] = payload

                        response = await client.post(
                            f"{self.base_url}{endpoint}", json=test_data, timeout=5.0
                        )

                        # Check if payload is reflected in response
                        if payload in response.text:
                            self.add_finding(
                                severity="MEDIUM",
                                title=f"Potential XSS - {endpoint}",
                                description=f"User input is reflected in response without sanitization",
                                service="Gateway",
                                endpoint=endpoint,
                                evidence=f"Payload: {payload} reflected in response",
                                recommendation="Sanitize all user inputs before displaying. Implement Content Security Policy (CSP) headers.",
                            )
                            break

                    except Exception as e:
                        print(f"  Error testing XSS on {endpoint}: {e}")

    async def test_file_upload_vulnerabilities(self):
        """Test file upload endpoints for vulnerabilities."""
        print("\n[TEST] File Upload Vulnerability Testing...")
        self.test_results["tests_run"] += 1

        # Test malicious file uploads
        test_files = [
            ("malicious.php", b"<?php system($_GET['cmd']); ?>", "application/x-php"),
            ("malicious.exe", b"MZ\x90\x00", "application/x-msdownload"),
            (
                "large_file.bin",
                b"X" * (100 * 1024 * 1024),
                "application/octet-stream",
            ),  # 100MB
        ]

        async with httpx.AsyncClient(timeout=30.0) as client:
            for filename, content, content_type in test_files:
                try:
                    files = {"file": (filename, content, content_type)}
                    response = await client.post(
                        f"{self.base_url}/api/v1/audio/transcribe",
                        files=files,
                        timeout=30.0,
                    )

                    # Check if malicious file was accepted
                    if response.status_code == 200:
                        if filename.endswith(".php") or filename.endswith(".exe"):
                            self.add_finding(
                                severity="HIGH",
                                title="Malicious File Upload Accepted",
                                description=f"Endpoint accepted {filename} which should be rejected",
                                service="Gateway",
                                endpoint="/api/v1/audio/transcribe",
                                evidence=f"File {filename} was accepted (status 200)",
                                recommendation="Implement strict file type validation (MIME type checking, not just extension). Reject executable files.",
                            )
                        elif len(content) > 10 * 1024 * 1024:  # > 10MB
                            self.add_finding(
                                severity="MEDIUM",
                                title="Large File Upload Accepted",
                                description=f"Endpoint accepted very large file ({len(content)} bytes) without size limits",
                                service="Gateway",
                                endpoint="/api/v1/audio/transcribe",
                                evidence=f"File size: {len(content)} bytes",
                                recommendation="Implement file size limits to prevent DoS attacks",
                            )

                except httpx.TimeoutException:
                    print(f"  Timeout testing {filename} (expected for large files)")
                except Exception as e:
                    print(f"  Error testing {filename}: {e}")

    async def test_rate_limiting(self):
        """Test rate limiting implementation."""
        print("\n[TEST] Rate Limiting Testing...")
        self.test_results["tests_run"] += 1

        # Test if rate limiting is properly enforced
        endpoint = "/api/v1/llm/generate"
        requests_per_minute = 100  # Try to exceed rate limit

        async with httpx.AsyncClient() as client:
            success_count = 0
            rate_limited_count = 0

            for i in range(requests_per_minute):
                try:
                    response = await client.post(
                        f"{self.base_url}{endpoint}",
                        json={"prompt": f"test {i}"},
                        timeout=2.0,
                    )

                    if response.status_code == 200:
                        success_count += 1
                    elif response.status_code == 429:
                        rate_limited_count += 1
                        break  # Rate limiting is working

                except Exception as e:
                    pass

            if success_count > 50 and rate_limited_count == 0:
                self.add_finding(
                    severity="MEDIUM",
                    title="Rate Limiting Not Enforced",
                    description=f"Endpoint {endpoint} accepted {success_count} requests without rate limiting",
                    service="Gateway",
                    endpoint=endpoint,
                    evidence=f"Accepted {success_count} requests without 429 response",
                    recommendation="Ensure rate limiting is properly configured and enforced for all endpoints",
                )
            else:
                print(
                    f"  ✓ Rate limiting appears to be working ({rate_limited_count} rate-limited responses)"
                )

    async def test_security_headers(self):
        """Test for missing security headers."""
        print("\n[TEST] Security Headers Testing...")
        self.test_results["tests_run"] += 1

        required_headers = {
            "X-Frame-Options": "DENY or SAMEORIGIN",
            "X-Content-Type-Options": "nosniff",
            "X-XSS-Protection": "1; mode=block",
            "Strict-Transport-Security": "max-age=...",
            "Content-Security-Policy": "default-src 'self'...",
            "Referrer-Policy": "strict-origin-when-cross-origin",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self.base_url}/health", timeout=5.0)

            missing_headers = []
            for header, expected in required_headers.items():
                if header not in response.headers:
                    missing_headers.append(header)

            if missing_headers:
                self.add_finding(
                    severity="HIGH",
                    title="Missing Security Headers",
                    description=f"The following security headers are missing: {', '.join(missing_headers)}",
                    service="Gateway",
                    endpoint="/health",
                    evidence=f"Missing headers: {missing_headers}",
                    recommendation="Add comprehensive security headers middleware to all HTTP responses",
                )
            else:
                print("  ✓ All required security headers present")

    async def test_grpc_security(self):
        """Test gRPC services for security issues."""
        print("\n[TEST] gRPC Security Testing...")
        self.test_results["tests_run"] += 1

        # Test if gRPC uses insecure channels
        services = [
            ("inference-api", "localhost:50051"),
            ("stt", "localhost:50052"),
            ("tts", "localhost:50053"),
        ]

        for service_name, address in services:
            try:
                # Try to connect with insecure channel
                channel = grpc.insecure_channel(address)

                # Check if channel is actually insecure
                # In a secure setup, this should fail or use TLS
                try:
                    grpc.channel_ready_future(channel).result(timeout=2.0)
                    self.add_finding(
                        severity="HIGH",
                        title=f"gRPC Insecure Channel - {service_name}",
                        description=f"Service {service_name} uses insecure gRPC channel (no TLS)",
                        service=service_name,
                        endpoint=address,
                        evidence=f"Successfully connected to {address} with insecure channel",
                        recommendation="Enable TLS for all gRPC connections. Use grpc.secure_channel() with proper certificates.",
                    )
                except Exception:
                    print(f"  ✓ {service_name} channel connection test completed")

                channel.close()

            except Exception as e:
                print(f"  Error testing {service_name}: {e}")

    async def test_privilege_escalation(self):
        """Test for privilege escalation vulnerabilities."""
        print("\n[TEST] Privilege Escalation Testing...")
        self.test_results["tests_run"] += 1

        # This would require actual authentication tokens
        # For now, we'll document the test approach
        print("  Note: Privilege escalation testing requires authenticated sessions")
        print(
            "  Manual testing recommended: Try accessing admin endpoints with regular user tokens"
        )

        # Document test cases
        test_cases = [
            "Regular user accessing /admin/users",
            "Regular user accessing /admin/conversations",
            "Regular user modifying other users' data",
            "Regular user accessing system configuration",
        ]

        print("  Test cases to verify manually:")
        for case in test_cases:
            print(f"    - {case}")

    async def run_all_tests(self):
        """Run all penetration tests."""
        print("=" * 80)
        print("PENETRATION TESTING - June Agent System")
        print("=" * 80)
        print(f"Target: {self.base_url}")
        print(f"Started: {datetime.now().isoformat()}\n")

        # Run all tests
        await self.test_cors_configuration()
        await self.test_authentication_bypass()
        await self.test_sql_injection()
        await self.test_xss_vulnerabilities()
        await self.test_file_upload_vulnerabilities()
        await self.test_rate_limiting()
        await self.test_security_headers()
        await self.test_grpc_security()
        await self.test_privilege_escalation()

        # Generate summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Tests Run: {self.test_results['tests_run']}")
        print(f"Vulnerabilities Found: {self.test_results['vulnerabilities_found']}")
        print(f"  Critical: {self.test_results['critical']}")
        print(f"  High: {self.test_results['high']}")
        print(f"  Medium: {self.test_results['medium']}")
        print(f"  Low: {self.test_results['low']}")
        print("=" * 80)

        return self.test_results

    def generate_report(self, output_file: str = "penetration_test_results.json"):
        """Generate JSON report of test results."""
        output_path = Path(__file__).parent.parent / "docs" / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w") as f:
            json.dump(self.test_results, f, indent=2)

        print(f"\nReport saved to: {output_path}")
        return output_path


async def main():
    """Main entry point."""
    base_url = os.getenv("GATEWAY_URL", "http://localhost:8000")

    tester = PenetrationTester(base_url=base_url)
    results = await tester.run_all_tests()
    report_path = tester.generate_report()

    # Exit with error code if critical or high severity issues found
    if results["critical"] > 0 or results["high"] > 0:
        print("\n⚠️  Critical or High severity vulnerabilities found!")
        sys.exit(1)
    else:
        print("\n✓ No critical or high severity vulnerabilities found")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
