import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import javafx.application.Application;
import javafx.application.Platform;
import javafx.geometry.Point2D;
import javafx.scene.Scene;
import javafx.scene.canvas.Canvas;
import javafx.scene.canvas.GraphicsContext;
import javafx.scene.control.Button;
import javafx.scene.image.Image;
import javafx.scene.input.MouseButton;
import javafx.scene.input.ScrollEvent;
import javafx.scene.layout.Pane;
import javafx.scene.paint.Color;
import javafx.scene.shape.Circle;
import javafx.scene.shape.Polyline;
import javafx.stage.Stage;

import java.io.File;
import java.io.IOException;
import java.nio.file.*;
import java.util.ArrayList;
import java.util.List;

/**
 * Floorplan viewer with route overlay.
 * - Background: floorplan.png (exported from CAD)
 * - Data: route.json { current:{x,y}, path:[{x,y}...], allNodes:[{id,x,y}...] }
 * - Current node: red circle
 * - Path: yellow polyline
 * - Nodes: clickable buttons (optional)
 * - Pan (drag) & Zoom (wheel)
 */
public class Main extends Application {

    // ---- Files ----
    private static final String FLOOR_IMG = "floorplan.png";
    private static final String ROUTE_JSON = "route.json";

    // ---- Affine mapping: CAD(x,y) -> Pixel(X,Y) ----
    // Xpix = (x - x0) * scale + offsetX
    // Ypix = (y0 - y) * scale + offsetY   // 화면 Y는 아래로 증가하므로 y축 뒤집기
    private double x0 = 0;          // CAD 기준 원점 x (도면 좌표)
    private double y0 = 0;          // CAD 기준 원점 y
    private double scale = 20.0;    // 1 CAD 단위당 픽셀(임시값, 이미지에 맞춰 조정)
    private double offsetX = 50;    // 화면 내 여백
    private double offsetY = 50;

    // Pan/Zoom state
    private double panX = 0, panY = 0;
    private double zoom = 1.0;

    // UI
    private Pane root;
    private Image bg;
    private Canvas bgCanvas;
    private Polyline pathLine;
    private Circle currentCircle;
    private Pane nodesLayer;

    // Data
    private final ObjectMapper om = new ObjectMapper();
    private List<Point2D> pathCad = new ArrayList<>();
    private Point2D currentCad = null;
    private List<NodeInfo> allNodes = new ArrayList<>();

    static class NodeInfo {
        String id; double x; double y;
        NodeInfo(String id, double x, double y){this.id=id;this.x=x;this.y=y;}
    }

    public static void main(String[] args) {
        launch(args);
    }

    @Override public void start(Stage stage){
        // Load background image
        File imgFile = new File(FLOOR_IMG);
        if (!imgFile.exists()) {
            System.err.println("Missing " + FLOOR_IMG + " next to the executable.");
        }
        bg = new Image(imgFile.exists() ? imgFile.toURI().toString() : null);

        root = new Pane();
        bgCanvas = new Canvas(bg.getWidth(), bg.getHeight());
        root.getChildren().add(bgCanvas);

        // Layers for vector overlays
        pathLine = new Polyline();
        pathLine.setStroke(Color.YELLOW);
        pathLine.setStrokeWidth(3);
        pathLine.setMouseTransparent(true);

        currentCircle = new Circle(6, Color.RED);
        currentCircle.setStroke(Color.WHITE);
        currentCircle.setStrokeWidth(1.5);
        currentCircle.setVisible(false);
        currentCircle.setMouseTransparent(true);

        nodesLayer = new Pane();

        root.getChildren().addAll(pathLine, currentCircle, nodesLayer);

        Scene scene = new Scene(root, Math.max(1200, bg.getWidth()), Math.max(800, bg.getHeight()));
        stage.setTitle("Floorplan Route Viewer");
        stage.setScene(scene);
        stage.show();

        drawBackground();
        enablePanZoom(scene);

        // First load & render
        loadRouteJson();
        renderAll();

        // Watch route.json changes
        startJsonWatcher();
    }

    // --- Render background with pan/zoom ---
    private void drawBackground() {
        GraphicsContext g = bgCanvas.getGraphicsContext2D();
        g.setTransform(1,0,0,1,0,0); // reset
        g.clearRect(0,0,bgCanvas.getWidth(), bgCanvas.getHeight());

        // Resize canvas to image size (once)
        bgCanvas.setWidth(bg.getWidth());
        bgCanvas.setHeight(bg.getHeight());

        // Apply pan/zoom via canvas translate+scale
        root.setTranslateX(panX);
        root.setTranslateY(panY);
        root.setScaleX(zoom);
        root.setScaleY(zoom);

        g.drawImage(bg, 0, 0);
    }

    // --- Pan & Zoom handlers ---
    private void enablePanZoom(Scene scene){
        final double[] last = new double[2];
        scene.setOnMousePressed(e -> {
            if (e.getButton() == MouseButton.MIDDLE || (e.getButton()==MouseButton.PRIMARY && e.isAltDown())) {
                last[0]=e.getSceneX(); last[1]=e.getSceneY();
            }
        });
        scene.setOnMouseDragged(e -> {
            if (e.getButton() == MouseButton.MIDDLE || (e.isPrimaryButtonDown() && e.isAltDown())) {
                panX += (e.getSceneX()-last[0]);
                panY += (e.getSceneY()-last[1]);
                last[0]=e.getSceneX(); last[1]=e.getSceneY();
                drawBackground();
                renderAll();
            }
        });
        scene.addEventFilter(ScrollEvent.SCROLL, e -> {
            double factor = (e.getDeltaY()>0)? 1.1 : 0.9;
            zoom *= factor;
            if (zoom < 0.2) zoom = 0.2;
            if (zoom > 5.0) zoom = 5.0;
            drawBackground();
            renderAll();
            e.consume();
        });
    }

    // --- Core: CAD(x,y) -> screen pixel (after affine, before pan/zoom which is applied to whole root) ---
    private Point2D cadToPixel(double x, double y){
        double X = (x - x0) * scale + offsetX;
        double Y = (y0 - y) * scale + offsetY; // invert y-axis
        return new Point2D(X, Y);
    }

    // --- Load JSON ---
    private void loadRouteJson(){
        File f = new File(ROUTE_JSON);
        if (!f.exists()) return;
        try {
            JsonNode root = om.readTree(f);
            // optional: load mapping parameters from JSON if you prefer
            // x0, y0, scale, offsetX, offsetY

            // current
            JsonNode cur = root.get("current");
            currentCad = (cur!=null)? new Point2D(cur.get("x").asDouble(), cur.get("y").asDouble()) : null;

            // path
            pathCad.clear();
            JsonNode arr = root.get("path");
            if (arr!=null && arr.isArray()){
                for (JsonNode n: arr){
                    pathCad.add(new Point2D(n.get("x").asDouble(), n.get("y").asDouble()));
                }
            }

            // allNodes
            allNodes.clear();
            JsonNode nodes = root.get("allNodes");
            if (nodes!=null && nodes.isArray()){
                for (JsonNode n: nodes){
                    String id = n.has("id")? n.get("id").asText() : "";
                    allNodes.add(new NodeInfo(id, n.get("x").asDouble(), n.get("y").asDouble()));
                }
            }
        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    // --- Render overlays ---
    private void renderAll(){
        // Path
        pathLine.getPoints().clear();
        for (Point2D p : pathCad){
            Point2D s = cadToPixel(p.getX(), p.getY());
            pathLine.getPoints().addAll(s.getX(), s.getY());
        }

        // Current
        if (currentCad != null){
            Point2D s = cadToPixel(currentCad.getX(), currentCad.getY());
            currentCircle.setCenterX(s.getX());
            currentCircle.setCenterY(s.getY());
            currentCircle.setRadius(6);
            currentCircle.setVisible(true);
        } else {
            currentCircle.setVisible(false);
        }

        // Nodes (as buttons)
        nodesLayer.getChildren().clear();
        for (NodeInfo n : allNodes){
            Point2D s = cadToPixel(n.x, n.y);
            Button b = new Button(n.id==null? "" : n.id);
            b.setStyle("-fx-background-color: #2e7d32; -fx-text-fill: white; -fx-font-size: 10; -fx-padding: 2 6 2 6; -fx-background-radius: 12;");
            b.setLayoutX(s.getX()-14);
            b.setLayoutY(s.getY()-14);
            b.setOnAction(e -> {
                // 예: 버튼 클릭 시 그 노드를 '현재 위치'로 설정
                currentCad = new Point2D(n.x, n.y);
                renderAll();
            });
            nodesLayer.getChildren().addAll(b);
        }
    }

    // --- Watch route.json for changes and live-reload ---
    private void startJsonWatcher(){
        Thread t = new Thread(() -> {
            try {
                Path p = Paths.get(".").toAbsolutePath().normalize();
                WatchService ws = FileSystems.getDefault().newWatchService();
                p.register(ws, StandardWatchEventKinds.ENTRY_CREATE, StandardWatchEventKinds.ENTRY_MODIFY);

                while (true){
                    WatchKey key = ws.take();
                    for (WatchEvent<?> ev : key.pollEvents()){
                        WatchEvent.Kind<?> kind = ev.kind();
                        Path file = (Path) ev.context();
                        if (file != null && file.toString().equals(ROUTE_JSON) &&
                                (kind == StandardWatchEventKinds.ENTRY_CREATE || kind == StandardWatchEventKinds.ENTRY_MODIFY)) {
                            Platform.runLater(() -> {
                                loadRouteJson();
                                renderAll();
                            });
                        }
                    }
                    key.reset();
                }
            } catch (Exception e) {
                e.printStackTrace();
            }
        }, "route-json-watcher");
        t.setDaemon(true);
        t.start();
    }
}
