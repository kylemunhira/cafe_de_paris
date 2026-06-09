class ZimraConfigurationError(Exception):
    pass


class ZimraSubmissionError(Exception):
    def __init__(self, message, *, status_code=None, response_body=None):
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body
