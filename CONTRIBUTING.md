# Contributing to S/4HANA MCP Server

Thank you for your interest in contributing to the S/4HANA MCP Server project! This document provides guidelines for contributing to this project.

## Code of Conduct

This project adheres to a code of conduct. By participating, you are expected to uphold this code.

## How to Contribute

### Reporting Issues

- Use GitHub Issues to report bugs or request features
- Search existing issues before creating a new one
- Provide detailed information including:
  - Steps to reproduce
  - Expected vs actual behavior
  - Environment details (OS, Python version, etc.)
  - Error messages or logs

### Development Process

1. **Fork the repository**
2. **Create a feature branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the coding standards
4. **Test your changes** thoroughly
5. **Commit your changes** with clear commit messages
6. **Push to your fork** and create a Pull Request

### Coding Standards

- Follow PEP 8 for Python code style
- Use meaningful variable and function names
- Add docstrings for functions and classes
- Include type hints where appropriate
- Keep functions focused and small
- Add comments for complex logic

### Testing

- Write unit tests for new functionality
- Ensure all existing tests pass
- Test with actual S/4HANA system when possible
- Include integration tests for MCP protocol compliance

### Documentation

- Update README.md if adding new features
- Document new MCP tools in the manifest.json
- Add examples for new functionality
- Update API documentation

### Pull Request Process

1. Ensure your PR has a clear title and description
2. Reference any related issues
3. Include screenshots for UI changes
4. Ensure all checks pass
5. Request review from maintainers

### Development Setup

1. Clone your fork:
   ```bash
   git clone https://github.com/your-username/s4hanaopn_mcpserver.git
   ```

2. Create virtual environment:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # If available
   ```

4. Copy configuration:
   ```bash
   cp local.settings.json.template local.settings.json
   # Edit local.settings.json with your S/4HANA details
   ```

### Commit Message Guidelines

- Use present tense ("Add feature" not "Added feature")
- Keep first line under 50 characters
- Reference issues with #issue-number
- Include detailed description if needed

Example:
```
Add sales order approval workflow

- Implement create_so_request tool
- Add approval/rejection functionality  
- Update manifest with new tools
- Add storage layer for request tracking

Fixes #123
```

### Release Process

- Releases follow semantic versioning (x.y.z)
- Version updates require updating manifest.json
- Release notes should include breaking changes
- Tag releases in Git

## Getting Help

- Check existing documentation first
- Search closed issues for similar problems
- Create a new issue with detailed information
- Reach out to maintainers for complex questions

## Recognition

Contributors will be recognized in:
- README.md contributors section
- Release notes for significant contributions
- GitHub contributors page

Thank you for contributing to making S/4HANA integration with AI assistants better!
