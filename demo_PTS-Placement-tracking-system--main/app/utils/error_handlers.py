from flask import jsonify


def register_error_handlers(app) -> None:
    @app.errorhandler(404)
    def handle_not_found(error):
        return jsonify({"success": False, "message": "Resource not found", "data": None, "errors": {"detail": str(error)}, "meta": {}}), 404

    @app.errorhandler(400)
    def handle_bad_request(error):
        return jsonify({"success": False, "message": "Bad request", "data": None, "errors": {"detail": str(error)}, "meta": {}}), 400

    @app.errorhandler(500)
    def handle_internal_error(error):
        return jsonify({"success": False, "message": "Internal server error", "data": None, "errors": {"detail": "An unexpected error occurred"}, "meta": {}}), 500
